import argparse
import time
from pathlib import Path
import numpy as np
from scipy.optimize import linprog

EPS = 1e-9
DEFAULT_FOLDER = 'dataset/converted69'
DEFAULT_ALPHA = 2.0
DEFAULT_REPEATS = 1
METHODS = ('LCM', 'VAM', 'AVG-LCM', 'CSM', 'RBSM', 'SAM', 'SSM')


def read_tp(path):
    t = Path(path).read_text().split()
    if len(t) < 2:
        raise ValueError('File terlalu pendek')
    m, n = int(t[0]), int(t[1])
    if m <= 0 or n <= 0 or len(t) != 2 + m*n + m + n:
        raise ValueError('Dimensi atau jumlah elemen tidak valid')
    a = np.array([float(v) for v in t[2:]], dtype=float)
    if not np.all(np.isfinite(a)) or np.any(a < 0):
        raise ValueError('Input tidak finite atau negatif')
    c = a[:m*n].reshape(m, n)
    s = a[m*n:m*n+m].copy()
    d = a[m*n+m:].copy()
    if not np.isclose(s.sum(), d.sum(), rtol=1e-9, atol=1e-7):
        raise ValueError('TP tidak balanced')
    return c, s, d


def solve_optimal(c, s, d):
    m, n = c.shape
    a = np.zeros((m+n, m*n))
    for i in range(m):
        a[i, i*n:(i+1)*n] = 1
    for j in range(n):
        a[m+j, j::n] = 1
    r = linprog(c.ravel(), A_eq=a, b_eq=np.r_[s, d], bounds=(0, None), method='highs')
    if not r.success:
        raise RuntimeError(r.message)
    return float(r.fun)


def validate(x, s, d):
    return (np.all(x >= -EPS) and np.allclose(x.sum(axis=1), s, atol=1e-6, rtol=1e-9)
            and np.allclose(x.sum(axis=0), d, atol=1e-6, rtol=1e-9))


def result(c, x, it):
    return float(np.sum(c*x)), x, it


def solve_lcm(c, supply, demand):
    s, d = supply.copy(), demand.copy()
    x = np.zeros_like(c)
    it = 0
    while True:
        rows, cols = np.flatnonzero(s > EPS), np.flatnonzero(d > EPS)
        if not len(rows) or not len(cols):
            return result(c, x, it)
        _, _, i, j = min((c[i,j], -min(s[i],d[j]), i,j) for i in rows for j in cols)
        z = min(s[i], d[j]); x[i,j] += z; s[i] -= z; d[j] -= z
        it += 1


def solve_vam(c, supply, demand):
    s, d = supply.copy(), demand.copy()
    x = np.zeros_like(c)
    it = 0
    while True:
        rows, cols = np.flatnonzero(s > EPS), np.flatnonzero(d > EPS)
        if not len(rows) or not len(cols):
            return result(c,x,it)
        candidates = []
        for i in rows:
            a = np.sort(c[i,cols]); penalty = a[1]-a[0] if len(a)>1 else a[0]
            j = min(cols, key=lambda j: (c[i,j],-min(s[i],d[j]),j))
            candidates.append((-penalty,c[i,j],-min(s[i],d[j]),i,j))
        for j in cols:
            a = np.sort(c[rows,j]); penalty = a[1]-a[0] if len(a)>1 else a[0]
            i = min(rows, key=lambda i: (c[i,j],-min(s[i],d[j]),i))
            candidates.append((-penalty,c[i,j],-min(s[i],d[j]),i,j))
        _,_,_,i,j = min(candidates)
        z = min(s[i],d[j]); x[i,j] += z; s[i] -= z; d[j] -= z
        it += 1


def solve_avg_lcm(c, supply, demand, alpha=2.0):
    s, d = supply.copy(), demand.copy()
    x = np.zeros_like(c)
    ar, ac = s>EPS, d>EPS
    rs, cs = c[:,ac].sum(axis=1), c[ar,:].sum(axis=0)
    nr, nc = int(ar.sum()), int(ac.sum())
    it = 0
    while nr and nc:
        ra, ca = rs/nc, cs/nr
        rows, cols = np.flatnonzero(ar),np.flatnonzero(ac)
        _,_,_,i,j = min((c[i,j]-alpha*(ra[i]+ca[j])/2,c[i,j],-min(s[i],d[j]),i,j)
                         for i in rows for j in cols)
        z = min(s[i],d[j]); x[i,j] += z; s[i] -= z; d[j] -= z
        it += 1
        if s[i] <= EPS and ar[i]:
            ar[i] = False; nr -= 1; cs -= c[i,:]
        if d[j] <= EPS and ac[j]:
            ac[j] = False; nc -= 1; rs -= c[:,j]
    return result(c,x,it)


# CSM/RBSM/SAM/SSM mengikuti pola minimum-per-kolom lalu redistribusi.
# Implementasi ini menjaga kelayakan dan menghindari indeks tak terinisialisasi
# yang ada di beberapa cabang kode C/C++ sumber. Ini port terkontrol,
# bukan jaminan output identik pada semua tie-case dengan sumber aslinya.

def solve_reallocation(c, supply, demand, variant, max_iter=None):
    m,n = c.shape
    x = np.zeros_like(c)
    tc = c.sum(axis=1)
    # Inisialisasi: seluruh demand ditempatkan di baris termurah tiap kolom.
    # CSM/RBSM: tie -> TC lebih besar. SAM: mean*original_supply lebih besar.
    for j in range(n):
        if variant in ('CSM','RBSM'):
            i = min(range(m), key=lambda i: (c[i,j], -tc[i],i))
        elif variant == 'SAM':
            priority = c.mean(axis=1)*supply
            i = min(range(m), key=lambda i: (c[i,j], -priority[i],i))
        else:
            i = min(range(m), key=lambda i: (c[i,j],i))
        x[i,j] = demand[j]

    priority = {'CSM': tc*supply, 'RBSM': tc*supply,
                'SAM': c.mean(axis=1)*supply, 'SSM': supply}
    weight = priority[variant]
    it=0
    if max_iter is None:
        max_iter = max(100, 20*m*n + 10*m)
    seen = set()

    while True:
        totals = x.sum(axis=1)
        excess = totals-supply
        over = np.flatnonzero(excess > EPS)
        under = np.flatnonzero(excess < -EPS)
        if not len(over) and not len(under):
            return result(c,x,it)
        if not len(over) or not len(under):
            raise RuntimeError(f'{variant}: alokasi tak seimbang')
        if it >= max_iter:
            raise RuntimeError(f'{variant}: batas iterasi {max_iter}')
        # Cek siklus untuk data integer; gerakan identik diulang berarti buntu.
        signature = tuple(np.round(x.ravel(),8))
        if signature in seen:
            raise RuntimeError(f'{variant}: siklus redistribusi')
        seen.add(signature)

        # Kandidat: donor di baris excess dengan alokasi positif dan
        # penerima di baris under pada kolom sama. 'diff' biaya minimum.
        candidates=[]
        for j in range(n):
            donors = [i for i in over if x[i,j] > EPS]
            if not donors: continue
            # pilih local best tiap kolom, mengikuti struktur sumber
            local = []
            for i in donors:
                for k in under:
                    diff = abs(c[i,j]-c[k,j])
                    z = min(x[i,j], excess[i], -excess[k])
                    if z > EPS:
                        # tie: TC penerima lebih besar, lalu indeks
                        local.append((diff, -tc[k], i, k, j, z))
            if local:
                best_local = min(local, key=lambda t:(t[0],t[1],t[2],t[3]))
                candidates.append(best_local)
        if not candidates:
            raise RuntimeError(f'{variant}: tidak ada kandidat pemindahan yang feasible')

        # Kolom diprioritaskan menurut selisih cost minimum.
        # Pada tie, pertimbangkan kapasitas donasi dan bobot varian.
        if variant == 'CSM':
            key = lambda t:(t[0], -min(t[5], abs(excess[t[2]]) if weight[t[2]]>=weight[t[3]] else -excess[t[3]])*c[t[3],t[4]],t[4])
        elif variant == 'RBSM':
            key = lambda t:(t[0], -min(t[5], abs(excess[t[2]]) if weight[t[2]]>=weight[t[3]] else -excess[t[3]])*c[t[2],t[4]],t[4])
        else:
            key = lambda t:(t[0], -x[t[2],t[4]], t[4])
        _,_,i,k,j,z = min(candidates,key=key)
        # Transaksi aman: tidak melebihi kelebihan donor / kebutuhan penerima.
        x[i,j]-=z; x[k,j]+=z
        it+=1


def solve_csm(c,s,d): return solve_reallocation(c,s,d,'CSM')
def solve_rbsm(c,s,d): return solve_reallocation(c,s,d,'RBSM')
def solve_sam(c,s,d): return solve_reallocation(c,s,d,'SAM')
def solve_ssm(c,s,d): return solve_reallocation(c,s,d,'SSM')


def measure_runtime(solver,c,s,d,repeats):
    solver(c,s,d)  # warm-up
    times=[]
    for _ in range(repeats):
        t=time.perf_counter_ns(); solver(c,s,d)
        times.append((time.perf_counter_ns()-t)/1e6)
    return times


def benchmark(folder,alpha,repeats,show_allocation=False):
    files=sorted(Path(folder).glob('*.in'))
    if not files:
        print(f'Tidak ada file .in di {folder}'); return
    solvers={'LCM':solve_lcm,'VAM':solve_vam,
             'AVG-LCM':lambda c,s,d:solve_avg_lcm(c,s,d,alpha),
             'CSM':solve_csm,'RBSM':solve_rbsm,'SAM':solve_sam,'SSM':solve_ssm}
    stats={name:{'optimal':0,'gaps':[],'times':[],'iterations':[], 'success':0,
                 'win':0,'tie':0,'loss':0,'errors':0} for name in solvers}
    print('='*143)
    print(f'BENCHMARK 7 METODE | Folder: {folder} | Alpha: {alpha} | Repeats: {repeats} | Files: {len(files)}')
    print('CATATAN: CSM/RBSM/SAM/SSM adalah port terkontrol; pastikan validasi terhadap output C/C++ asli.')
    print('='*143)
    print(f"{'FILE':<23}{'OPT LP':>12}{'LCM':>12}{'VAM':>12}{'AVG-LCM':>12}{'CSM':>12}{'RBSM':>12}{'SAM':>12}{'SSM':>12} {'ITER (LCM/VAM/AVG/CSM/RBSM/SAM/SSM)'}")
    print('-'*143)
    for file in files:
        try:
            c,s,d=read_tp(file); opt=solve_optimal(c,s,d)
        except Exception as e:
            print(f'[INPUT/LP ERROR] {file.name}: {e}'); continue
        case={}
        for name,solver in solvers.items():
            try:
                cost,x,it=solver(c,s,d)
                if not validate(x,s,d): raise RuntimeError('solusi tidak feasible')
                if cost < opt-1e-5: raise RuntimeError('biaya di bawah LP optimal')
                tt=measure_runtime(solver,c,s,d,repeats)
                gap=max(0.,100*(cost-opt)/abs(opt)) if abs(opt)>EPS else (0. if abs(cost)<EPS else float('inf'))
                good=bool(np.isclose(cost,opt,rtol=1e-8,atol=1e-6))
                case[name]=(cost,it)
                st=stats[name]; st['success']+=1; st['optimal']+=int(good)
                st['gaps'].append(gap);st['times'].extend(tt);st['iterations'].append(it)
                if show_allocation:
                    print(f'\n{file.name} - {name}: COST={cost:.2f}, ITER={it}, GAP={gap:.4f}%, AVG TIME={np.mean(tt):.5f} ms\n{x}')
            except Exception as e:
                stats[name]['errors']+=1
                case[name]=None
                print(f'[METHOD ERROR] {file.name} - {name}: {e}')
        base=case['LCM']
        if base is not None:
            for name in solvers:
                if name=='LCM' or case[name] is None: continue
                v=case[name][0]; lc=base[0]
                tag='win' if v<lc-1e-6 else 'loss' if v>lc+1e-6 else 'tie'
                stats[name][tag]+=1
        costs=''.join(f'{case[name][0]:>12.2f}' if case[name] else f'{"ERROR":>12}' for name in solvers)
        iters='/'.join(str(case[name][1]) if case[name] else '-' for name in solvers)
        print(f'{file.name:<23}{opt:>12.2f}{costs}  {iters}')

    print('\n'+'='*143+'\nRANGKUMAN AKHIR\n'+'='*143)
    print('alpha = '+str(DEFAULT_ALPHA))
    print(f"{'METHOD':<11}{'SUCCESS':>9}{'FAILED':>9}{'OPTIMAL':>10}{'OPT %':>10}{'AVG GAP %':>13}{'AVG ITER':>11}{'AVG TIME ms':>15}{'MED TIME ms':>15}{'MIN TIME ms':>15}{'MAX TIME ms':>15}")
    print('-'*143)
    for name,st in stats.items():
        n=st['success']
        if not n:
            print(f'{name:<11}{0:>9}{st["errors"]:>9}'+'  (tidak ada solusi valid)');continue
        t=st['times']
        print(f"{name:<11}{n:>9}{st['errors']:>9}{st['optimal']:>10}{100*st['optimal']/n:>9.2f}%{np.mean(st['gaps']):>12.4f}%{np.mean(st['iterations']):>11.2f}{np.mean(t):>15.5f}{np.median(t):>15.5f}{np.min(t):>15.5f}{np.max(t):>15.5f}")
    print('\nWIN/TIE/LOSS VS LCM (hanya testcase di mana kedua metode valid)')
    for name in solvers:
        if name!='LCM':
            st=stats[name];print(f'{name:<11} WIN={st["win"]} TIE={st["tie"]} LOSS={st["loss"]}')
    eligible=[n for n in solvers if stats[n]['success']==len(files)]
    print('\nKESIMPULAN (metode yang berhasil pada SEMUA file):')
    if eligible:
        print('Optimal terbanyak  :',max(eligible,key=lambda n:stats[n]['optimal']))
        print('AVG GAP terkecil   :',min(eligible,key=lambda n:np.mean(stats[n]['gaps'])))
        print('AVG ITER tersedikit:',min(eligible,key=lambda n:np.mean(stats[n]['iterations'])))
        print('AVG TIME tercepat  :',min(eligible,key=lambda n:np.mean(stats[n]['times'])))
    else:
        print('Tidak ada metode yang berhasil pada seluruh file; periksa ERROR sebelum membandingkan.')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--folder',default=DEFAULT_FOLDER)
    p.add_argument('--alpha',type=float,default=DEFAULT_ALPHA)
    p.add_argument('--repeats',type=int,default=DEFAULT_REPEATS)
    p.add_argument('--allocation',action='store_true')
    a=p.parse_args()
    if not np.isfinite(a.alpha) or a.alpha<0:p.error('alpha harus finite dan >=0')
    if a.repeats<1:p.error('repeats minimal 1')
    benchmark(a.folder,a.alpha,a.repeats,a.allocation)
