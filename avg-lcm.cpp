
#include <iostream>
#include <vector>
#include <algorithm>
#include <cfloat>
#include <cmath>

using namespace std;

int main() {
    // ================= INPUT MANUAL =================

    int n, m;
    double a = 2.0;

    cout << "Jumlah sumber (n): ";
    cin >> n;

    cout << "Jumlah tujuan (m): ";
    cin >> m;

    vector<vector<pair<int, bool>>> cost(
        n, vector<pair<int, bool>>(m, {0, true})
    );

    vector<int> supply(n);
    vector<int> demand(m);

    cout << "\nMasukkan matriks cost:\n";
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < m; j++) {
            cin >> cost[i][j].first;
        }
    }

    cout << "\nMasukkan supply:\n";
    for (int i = 0; i < n; i++) {
        cin >> supply[i];
    }

    cout << "\nMasukkan demand:\n";
    for (int i = 0; i < m; i++) {
        cin >> demand[i];
    }

    cout << "\nAlpha (default 2.0): ";
    cin >> a;

    double totalCost = 0;
    int iterations;
    int sumsupply = 0, sumdemand = 0;

    for (int i = 0; i < supply.size(); i++) {
        sumsupply += supply[i];
    }

    for (int i = 0; i < demand.size(); i++) {
        sumdemand += demand[i];
    }

    if (sumdemand != sumsupply) {
        cout << "imbalance";
        return 0;
    } else {
        cout << "Balance" << endl;
    }

    // ================= AVG-LCM =================

    vector<double> avgrow(n, 0);
    vector<double> avgcol(m, 0);

    for (iterations = 1; ; iterations++) {

        double sum;
        int count;

        // avg setiap row
        for (int i = 0; i < n; i++) {
            sum = 0;
            count = 0;

            for (int j = 0; j < m; j++) {
                if (cost[i][j].second) {
                    sum += cost[i][j].first;
                    count++;
                }
            }

            if (count > 0) avgrow[i] = sum / count;
        }

        // avg setiap column
        for (int j = 0; j < m; j++) {
            sum = 0;
            count = 0;

            for (int i = 0; i < n; i++) {
                if (cost[i][j].second) {
                    sum += cost[i][j].first;
                    count++;
                }
            }

            if (count > 0) avgcol[j] = sum / count;
        }

        // hitung score
        // score = c - a * ((avgrow + avgcol)/2)
        double score, minscore = DBL_MAX;
        pair<int, int> coor;

        for (int i = 0; i < n; i++) {
            for (int j = 0; j < m; j++) {
                if (cost[i][j].second) {

                    score = cost[i][j].first
                        - a * ((avgrow[i] + avgcol[j]) / 2);

                    if (score < minscore) {
                        minscore = score;
                        coor = {i, j};
                    }
                    else if (abs(score - minscore) <= 1e-9) {
                        // kalo score sama pilih cost terkecil
                        if (cost[i][j].first <
                            cost[coor.first][coor.second].first) {
                            coor = {i, j};
                        }
                        else if (cost[i][j].first ==
                                 cost[coor.first][coor.second].first) {
                            // kalo cost sama pilih aloc terbesar
                            int alocnew = min(supply[i], demand[j]);
                            int alocmin = min(
                                supply[coor.first],
                                demand[coor.second]
                            );

                            if (alocnew > alocmin) {
                                coor = {i, j};
                            }
                            else if (alocnew == alocmin) {
                                // kalo aloc sama pilih index row terkecil
                                if (i < coor.first) {
                                    coor = {i, j};
                                }
                                else if (i == coor.first) {
                                    // kalo index row sama pilih index col terkecil
                                    if (j == coor.second) {
                                        coor = {i, j};
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        int aloc = min(
            supply[coor.first],
            demand[coor.second]
        );

        totalCost += aloc * cost[coor.first][coor.second].first;

        // ================= PRINT ITERASI =================

        cout << "\nIterasi " << iterations << endl;
        cout << "Sel terpilih: S" << coor.first + 1
             << "-D" << coor.second + 1 << endl;

        cout << "Avg row: " << avgrow[coor.first] << endl;
        cout << "Avg col: " << avgcol[coor.second] << endl;
        cout << "Min score: " << minscore << endl;
        cout << "Alokasi: " << aloc << endl;
        cout << "Total cost sementara: " << totalCost << endl;

        // ================= UPDATE =================

        supply[coor.first] -= aloc;
        sumsupply -= aloc;

        demand[coor.second] -= aloc;
        sumdemand -= aloc;

        if (supply[coor.first] == 0) {
            for (int i = 0; i < m; i++) {
                cost[coor.first][i].second = false;
            }
        }

        if (demand[coor.second] == 0) {
            for (int i = 0; i < n; i++) {
                cost[i][coor.second].second = false;
            }
        }

        if (sumsupply == 0 && sumdemand == 0) {
            break;
        }
    }

    cout << "\n-------RESULT-------" << endl;
    cout << "Total cost: " << totalCost << endl;
    cout << "Iterations: " << iterations << endl;

    return 0;
}
