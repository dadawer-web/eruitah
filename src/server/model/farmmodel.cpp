#include "farmmodel.hpp"
#include "db.h"
#include <iostream>
#include <cstring>

bool FarmModel::initTable()
{
    const char *sql = "CREATE TABLE IF NOT EXISTS farm_user ("
                      "userid INT NOT NULL,"
                      "coins INT NOT NULL DEFAULT 0,"
                      "exp INT NOT NULL DEFAULT 0,"
                      "total_planted INT NOT NULL DEFAULT 0,"
                      "total_harvested INT NOT NULL DEFAULT 0,"
                      "total_answered INT NOT NULL DEFAULT 0,"
                      "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                      "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                      "PRIMARY KEY(userid)"
                      ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;";

    MySQL mysql;
    if (mysql.connect()) {
        if (!mysql.update(sql)) {
            return false;
        }
    }

    const char *sql2 = "CREATE TABLE IF NOT EXISTS farm_plot ("
                       "id INT AUTO_INCREMENT PRIMARY KEY,"
                       "ownerid INT NOT NULL,"
                       "plotindex INT NOT NULL,"
                       "state TINYINT NOT NULL DEFAULT 0,"
                       "question TEXT,"
                       "subject VARCHAR(10),"
                       "answererid INT DEFAULT NULL,"
                       "answer TEXT,"
                       "score INT DEFAULT NULL,"
                       "feedback TEXT,"
                       "planted_at TIMESTAMP NULL,"
                       "answered_at TIMESTAMP NULL,"
                       "harvested_at TIMESTAMP NULL,"
                       "UNIQUE KEY uk_owner_plot (ownerid, plotindex),"
                       "KEY idx_state (state),"
                       "KEY idx_ownerid (ownerid)"
                       ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;";

    if (mysql.connect()) {
        if (!mysql.update(sql2)) {
            return false;
        }
    }

    return true;
}

bool FarmModel::initUserFarm(int userid)
{
    char sql[256] = {0};
    sprintf(sql, "INSERT IGNORE INTO farm_user(userid) VALUES(%d)", userid);

    MySQL mysql;
    if (mysql.connect()) {
        if (mysql.update(sql)) {
            for (int i = 0; i < 9; ++i) {
                char plotSql[256] = {0};
                sprintf(plotSql, "INSERT IGNORE INTO farm_plot(ownerid, plotindex, state) VALUES(%d, %d, 0)", userid, i);
                MySQL plotMysql;
                if (plotMysql.connect()) {
                    plotMysql.update(plotSql);
                }
            }
            return true;
        }
    }
    return false;
}

FarmUser FarmModel::queryFarmUser(int userid)
{
    FarmUser fu = {userid, 0, 0, 0, 0, 0};

    char sql[256] = {0};
    sprintf(sql, "SELECT userid, coins, exp, total_planted, total_harvested, total_answered FROM farm_user WHERE userid=%d", userid);

    MySQL mysql;
    if (mysql.connect()) {
        MYSQL_RES *res = mysql.query(sql);
        if (res != nullptr) {
            MYSQL_ROW row = mysql_fetch_row(res);
            if (row != nullptr) {
                fu.userid = atoi(row[0]);
                fu.coins = atoi(row[1]);
                fu.exp = atoi(row[2]);
                fu.total_planted = atoi(row[3]);
                fu.total_harvested = atoi(row[4]);
                fu.total_answered = atoi(row[5]);
            }
            mysql_free_result(res);
        }
    }

    return fu;
}

bool FarmModel::updateFarmUserCoins(int userid, int coinsDelta)
{
    char sql[256] = {0};
    sprintf(sql, "UPDATE farm_user SET coins = coins + %d WHERE userid = %d", coinsDelta, userid);

    MySQL mysql;
    if (mysql.connect()) {
        return mysql.update(sql);
    }
    return false;
}

bool FarmModel::updateFarmUserExp(int userid, int expDelta)
{
    char sql[256] = {0};
    sprintf(sql, "UPDATE farm_user SET exp = exp + %d WHERE userid = %d", expDelta, userid);

    MySQL mysql;
    if (mysql.connect()) {
        return mysql.update(sql);
    }
    return false;
}

bool FarmModel::plantPlot(int ownerid, int plotindex, const string &question, const string &subject)
{
    char sql[1024] = {0};
    sprintf(sql, "UPDATE farm_plot SET state=1, question='%s', subject='%s', answererid=NULL, answer=NULL, score=NULL, feedback=NULL, planted_at=NOW() WHERE ownerid=%d AND plotindex=%d",
            question.c_str(), subject.c_str(), ownerid, plotindex);

    MySQL mysql;
    if (mysql.connect()) {
        return mysql.update(sql);
    }
    return false;
}

FarmPlot FarmModel::queryPlot(int ownerid, int plotindex)
{
    FarmPlot fp = {-1, ownerid, plotindex, 0, "", "", -1, "", -1, ""};

    char sql[512] = {0};
    sprintf(sql, "SELECT id, ownerid, plotindex, state, IFNULL(question,''), IFNULL(subject,''), IFNULL(answererid,-1), IFNULL(answer,''), IFNULL(score,-1), IFNULL(feedback,'') FROM farm_plot WHERE ownerid=%d AND plotindex=%d", ownerid, plotindex);

    MySQL mysql;
    if (mysql.connect()) {
        MYSQL_RES *res = mysql.query(sql);
        if (res != nullptr) {
            MYSQL_ROW row = mysql_fetch_row(res);
            if (row != nullptr) {
                fp.id = atoi(row[0]);
                fp.ownerid = atoi(row[1]);
                fp.plotindex = atoi(row[2]);
                fp.state = atoi(row[3]);
                fp.question = row[4];
                fp.subject = row[5];
                fp.answererid = atoi(row[6]);
                fp.answer = row[7];
                fp.score = atoi(row[8]);
                fp.feedback = row[9];
            }
            mysql_free_result(res);
        }
    }

    return fp;
}

vector<FarmPlot> FarmModel::queryPlotsByOwner(int ownerid)
{
    vector<FarmPlot> plots;

    char sql[512] = {0};
    sprintf(sql, "SELECT id, ownerid, plotindex, state, IFNULL(question,''), IFNULL(subject,''), IFNULL(answererid,-1), IFNULL(answer,''), IFNULL(score,-1), IFNULL(feedback,'') FROM farm_plot WHERE ownerid=%d ORDER BY plotindex", ownerid);

    MySQL mysql;
    if (mysql.connect()) {
        MYSQL_RES *res = mysql.query(sql);
        if (res != nullptr) {
            MYSQL_ROW row;
            while ((row = mysql_fetch_row(res)) != nullptr) {
                FarmPlot fp;
                fp.id = atoi(row[0]);
                fp.ownerid = atoi(row[1]);
                fp.plotindex = atoi(row[2]);
                fp.state = atoi(row[3]);
                fp.question = row[4];
                fp.subject = row[5];
                fp.answererid = atoi(row[6]);
                fp.answer = row[7];
                fp.score = atoi(row[8]);
                fp.feedback = row[9];
                plots.push_back(fp);
            }
            mysql_free_result(res);
        }
    }

    return plots;
}

bool FarmModel::updatePlotState(int ownerid, int plotindex, int state)
{
    char sql[256] = {0};
    sprintf(sql, "UPDATE farm_plot SET state=%d WHERE ownerid=%d AND plotindex=%d", state, ownerid, plotindex);

    MySQL mysql;
    if (mysql.connect()) {
        return mysql.update(sql);
    }
    return false;
}

bool FarmModel::answerPlot(int ownerid, int plotindex, int answererid, const string &answer, int score, const string &feedback)
{
    char sql[2048] = {0};
    sprintf(sql, "UPDATE farm_plot SET state=0, answererid=%d, answer='%s', score=%d, feedback='%s', harvested_at=NOW() WHERE ownerid=%d AND plotindex=%d",
            answererid, answer.c_str(), score, feedback.c_str(), ownerid, plotindex);

    MySQL mysql;
    if (mysql.connect()) {
        return mysql.update(sql);
    }
    return false;
}

bool FarmModel::harvestPlot(int ownerid, int plotindex)
{
    char sql[512] = {0};
    sprintf(sql, "UPDATE farm_plot SET state=0, question=NULL, subject=NULL, answererid=NULL, answer=NULL, score=NULL, feedback=NULL, harvested_at=NOW() WHERE ownerid=%d AND plotindex=%d AND state=2", ownerid, plotindex);

    MySQL mysql;
    if (mysql.connect()) {
        return mysql.update(sql);
    }
    return false;
}
