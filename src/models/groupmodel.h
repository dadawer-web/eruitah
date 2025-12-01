#ifndef GROUPMODEL_H
#define GROUPMODEL_H

#include "group.h"
#include <vector>
using namespace std;

/**
 * @brief The GroupModel class
 * 
 * Data access class for managing group information in the database.
 * Provides methods for group creation, membership management, and querying.
 */
class GroupModel {
public:
    /**
     * @brief Create a new chat group
     * @param group Group object containing group information
     * @return true if creation was successful, false otherwise
     */
    bool createGroup(Group &group);
    
    /**
     * @brief Add a user to a group
     * @param userid User ID to add
     * @param groupid Group ID to join
     * @param role Role assigned to the user in the group
     */
    void addGroup(int userid, int groupid, string role);
    
    /**
     * @brief Get all groups a user belongs to
     * @param userid User ID to query
     * @return Vector of Group objects
     */
    vector<Group> queryGroups(int userid);
    
    /**
     * @brief Get list of user IDs in a specific group (excluding the requesting user)
     * @param userid Requesting user ID (will be excluded from results)
     * @param groupid Group ID to query
     * @return Vector of user IDs in the group
     */
    vector<int> queryGroupUsers(int userid, int groupid);
};

#endif // GROUPMODEL_H