#ifndef OFFLINEMESSAGEMODEL_H
#define OFFLINEMESSAGEMODEL_H

#include <vector>
#include <string>
using namespace std;

/**
 * @brief The OfflineMsgModel class
 * 
 * Data access class for managing offline messages in the database.
 * Handles storing, retrieving, and deleting messages for offline users.
 */
class OfflineMsgModel {
public:
    /**
     * @brief Store an offline message for a user
     * @param userid User ID to receive the message
     * @param msg Message content (typically in JSON format)
     */
    void insert(int userid, string msg);
    
    /**
     * @brief Remove all offline messages for a user
     * @param userid User ID whose messages to delete
     * 
     * Typically called after a user logs in and their messages are delivered.
     */
    void remove(int userid);
    
    /**
     * @brief Retrieve all offline messages for a user
     * @param userid User ID to query
     * @return Vector of message strings
     */
    vector<string> query(int userid);
};

#endif // OFFLINEMESSAGEMODEL_H