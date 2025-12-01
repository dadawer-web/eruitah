#ifndef GROUP_H
#define GROUP_H

#include "groupuser.h"
#include <vector>
using namespace std;

/**
 * @brief The Group class
 * 
 * ORM (Object-Relational Mapping) class for the Group table in the database.
 * Represents a chat group with its members.
 */
class Group {
public:
    /**
     * @brief Constructor for Group class
     * @param id Group ID (default: -1 for new groups)
     * @param name Group name
     * @param desc Group description
     */
    Group(int id = -1, string name = "", string desc = "")
        : _id(id), _name(name), _desc(desc) {}

    // Setter methods
    void setId(int id) { this->_id = id; }
    void setName(string name) { this->_name = name; }
    void setDesc(string desc) { this->_desc = desc; }

    // Getter methods
    int getId() const { return this->_id; }
    string getName() const { return this->_name; }
    string getDesc() const { return this->_desc; }
    vector<GroupUser>& getUsers() { return this->users; }

private:
    int _id;            // Group ID
    string _name;       // Group name
    string _desc;       // Group description
    vector<GroupUser> users; // List of users in the group
};

#endif // GROUP_H