#ifndef FRIENDMODEL_H
#define FRIENDMODEL_H

#include "user.h"
#include <vector>
using namespace std;

/**
 * @brief The FriendModel class
 * 
 * Data access class for managing friend relationships in the database.
 * Provides methods for adding friends and retrieving friend lists.
 */
class FriendModel {
public:
    /**
     * @brief Create a new friend relationship
     * @param userid ID of the first user
     * @param friendid ID of the second user to be added as a friend
     * 
     * Establishes a bidirectional friendship between two users.
     */
    void insert(int userid, int friendid);
    
    /**
     * @brief Get all friends for a user
     * @param userid User ID to query
     * @return Vector of User objects representing the user's friends
     */
    vector<User> query(int userid);
};

#endif // FRIENDMODEL_H