#ifndef GROUPUSER_H
#define GROUPUSER_H

#include "user.h"

/**
 * @brief The GroupUser class
 * 
 * Represents a user within a chat group context, extending the base User class
 * with additional role information specific to group membership.
 */
class GroupUser : public User {
public:
    /**
     * @brief Set the role of the user in the group
     * @param role Role string (e.g., "creator" or "normal")
     */
    void setRole(string role) { this->role = role; }
    
    /**
     * @brief Get the role of the user in the group
     * @return Role string
     */
    string getRole() const { return this->role; }

private:
    string role; // Role information: creator/normal
};

#endif // GROUPUSER_H