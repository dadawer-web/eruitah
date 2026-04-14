#ifndef FARMMODEL_H
#define FARMMODEL_H

#include <vector>
#include <string>

using namespace std;

struct FarmPlot {
    int id;
    int ownerid;
    int plotindex;
    int state;
    string question;
    string subject;
    int answererid;
    string answer;
    int score;
    string feedback;
};

struct FarmUser {
    int userid;
    int coins;
    int exp;
    int total_planted;
    int total_harvested;
    int total_answered;
};

class FarmModel {
public:
    bool initTable();

    bool initUserFarm(int userid);
    FarmUser queryFarmUser(int userid);
    bool updateFarmUserCoins(int userid, int coinsDelta);
    bool updateFarmUserExp(int userid, int expDelta);

    bool plantPlot(int ownerid, int plotindex, const string &question, const string &subject);
    FarmPlot queryPlot(int ownerid, int plotindex);
    vector<FarmPlot> queryPlotsByOwner(int ownerid);
    bool updatePlotState(int ownerid, int plotindex, int state);
    bool answerPlot(int ownerid, int plotindex, int answererid, const string &answer, int score, const string &feedback);
    bool harvestPlot(int ownerid, int plotindex);
};

#endif
