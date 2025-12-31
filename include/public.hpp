#ifndef PUBLIC_H
#define PUBLIC_H

/**
 * @brief Common definitions shared between server and client
 * 
 * This header file contains enumerations and constants that must be
 * consistent across both server and client implementations.
 */

/**
 * @brief Message type enumeration
 * 
 * Defines all message types used in the chat application protocol.
 * Both server and client must use these identical values.
 */
enum EnMsgType
{
    LOGIN_MSG=1,            // Login request message
    LOGIN_MSG_ACK,          // Login response message
    LOGINOUT_MSG,           // Logout message
    REG_MSG,                // Registration request message
    REG_MSG_ACK,            // Registration response message
    ONE_CHAT_MSG,           // One-to-one chat message
    ADD_FRIEND_MSG,         // Add friend request message
    QUERY_FRIEND_MSG,       // Query friend list request message
    QUERY_FRIEND_MSG_ACK,   // Query friend list response message
    QUERY_GROUP_MSG,        // Query group list request message
    QUERY_GROUP_MSG_ACK,    // Query group list response message

    CREATE_GROUP_MSG,       // Create group request message
    CREATE_GROUP_MSG_ACK,   // Create group response message
    ADD_GROUP_MSG,          // Join group request message
    ADD_GROUP_MSG_ACK,      // Join group response message
    GROUP_CHAT_MSG,         // Group chat message
    
    // File transfer related message types
    FILE_TRANSFER_REQ=20,   // File transfer request
    FILE_TRANSFER_ACK,      // File transfer response
    FILE_TRANSFER_DATA,     // File data transfer
    FILE_TRANSFER_COMPLETE, // File transfer complete notification
    FILE_TRANSFER_ERROR,    // File transfer error notification
    
    // Emoji related message types
    UPLOAD_EMOJI_MSG,       // Upload emoji request message
    UPLOAD_EMOJI_MSG_ACK,   // Upload emoji response message
    QUERY_EMOJI_LIST_MSG,   // Query emoji list request message
    QUERY_EMOJI_LIST_MSG_ACK, // Query emoji list response message
    
    // Avatar related message types
    UPLOAD_AVATAR_MSG=40,   // Upload avatar request message
    UPLOAD_AVATAR_MSG_ACK,  // Upload avatar response message
    UPDATE_AVATAR_MSG,      // Update avatar request message
    UPDATE_AVATAR_MSG_ACK,  // Update avatar response message
    
    // User state update message type
    STATE_UPDATE_MSG        // User state update message
};
#endif