#ifndef USERMODEL_H
#define USERMODEL_H

#include "user.h"
/**
 * @brief The UserModel class
 * 
 * Data access class for the User table in the database.
 * Handles user creation, querying, and state management.
 */
class UserModel {
public:
    /**
     * @brief Insert a new user into the database
     * @param user User object containing registration information
     * @return true if insertion was successful, false otherwise
     */
    bool insert(User &user);

    /**
     * @brief Query user information by ID
     * @param id User identification number
     * @return User object with the requested information
     */
    User query(long long id);

    /**
     * @brief Update user status information
     * @param user User object with updated state information
     * @return true if update was successful, false otherwise
     */
    bool updateState(User user);

    /**
     * @brief Reset the online status of all users
     * 
     * Typically called when the server restarts to ensure clean state.
     */
    void resetState();
};

#endif // USERMODEL_H