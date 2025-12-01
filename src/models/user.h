#ifndef USER_H
#define USER_H

#include <string>
using namespace std;

/**
 * @brief The User class
 * 
 * ORM (Object-Relational Mapping) class for the User table in the database.
 * Represents a user in the chat system with basic information.
 */
class User {
public:
    /**
     * @brief Constructor for User class
     * @param id User identification number (default: -1 for new users)
     * @param name Username
     * @param pwd Password
     * @param state User state (default: "offline")
     */
    User(long long id = -1, string name = "", string pwd = "", string state = "offline")
        : _id(id), _name(name), _password(pwd), _state(state) {}

    // Setter methods
    void setId(long long id) { this->_id = id; }
    void setName(string name) { this->_name = name; }
    void setPwd(string pwd) { this->_password = pwd; }
    void setState(string state) { this->_state = state; }

    // Getter methods
    long long getId() const { return this->_id; }
    string getName() const { return this->_name; }
    string getPwd() const { return this->_password; }
    string getState() const { return this->_state; }

private:
    long long _id;         // User ID (supports large integers)
    string _name;          // Username
    string _password;      // Password
    string _state;         // State: online/offline
};

#endif // USER_H