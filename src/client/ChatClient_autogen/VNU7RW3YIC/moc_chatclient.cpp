/****************************************************************************
** Meta object code from reading C++ file 'chatclient.h'
**
** Created by: The Qt Meta Object Compiler version 67 (Qt 5.15.13)
**
** WARNING! All changes made in this file will be lost!
*****************************************************************************/

#include <memory>
#include "../../../chatclient.h"
#include <QtCore/qbytearray.h>
#include <QtCore/qmetatype.h>
#include <QtCore/QList>
#if !defined(Q_MOC_OUTPUT_REVISION)
#error "The header file 'chatclient.h' doesn't include <QObject>."
#elif Q_MOC_OUTPUT_REVISION != 67
#error "This file was generated using the moc from 5.15.13. It"
#error "cannot be used with the include files from this version of Qt."
#error "(The moc has changed too much.)"
#endif

QT_BEGIN_MOC_NAMESPACE
QT_WARNING_PUSH
QT_WARNING_DISABLE_DEPRECATED
struct qt_meta_stringdata_ChatClient_t {
    QByteArrayData data[59];
    char stringdata0[783];
};
#define QT_MOC_LITERAL(idx, ofs, len) \
    Q_STATIC_BYTE_ARRAY_DATA_HEADER_INITIALIZER_WITH_OFFSET(len, \
    qptrdiff(offsetof(qt_meta_stringdata_ChatClient_t, stringdata0) + ofs \
        - idx * sizeof(QByteArrayData)) \
    )
static const qt_meta_stringdata_ChatClient_t qt_meta_stringdata_ChatClient = {
    {
QT_MOC_LITERAL(0, 0, 10), // "ChatClient"
QT_MOC_LITERAL(1, 11, 9), // "connected"
QT_MOC_LITERAL(2, 21, 0), // ""
QT_MOC_LITERAL(3, 22, 12), // "disconnected"
QT_MOC_LITERAL(4, 35, 5), // "error"
QT_MOC_LITERAL(5, 41, 8), // "errorMsg"
QT_MOC_LITERAL(6, 50, 22), // "connectionStateChanged"
QT_MOC_LITERAL(7, 73, 13), // "loginResponse"
QT_MOC_LITERAL(8, 87, 7), // "success"
QT_MOC_LITERAL(9, 95, 7), // "message"
QT_MOC_LITERAL(10, 103, 15), // "messageReceived"
QT_MOC_LITERAL(11, 119, 6), // "fromId"
QT_MOC_LITERAL(12, 126, 8), // "fromName"
QT_MOC_LITERAL(13, 135, 7), // "isGroup"
QT_MOC_LITERAL(14, 143, 7), // "groupId"
QT_MOC_LITERAL(15, 151, 9), // "timestamp"
QT_MOC_LITERAL(16, 161, 20), // "groupMessageReceived"
QT_MOC_LITERAL(17, 182, 8), // "userName"
QT_MOC_LITERAL(18, 191, 17), // "friendListUpdated"
QT_MOC_LITERAL(19, 209, 11), // "QList<User>"
QT_MOC_LITERAL(20, 221, 7), // "friends"
QT_MOC_LITERAL(21, 229, 11), // "friendAdded"
QT_MOC_LITERAL(22, 241, 17), // "addFriendResponse"
QT_MOC_LITERAL(23, 259, 16), // "groupListUpdated"
QT_MOC_LITERAL(24, 276, 12), // "QList<Group>"
QT_MOC_LITERAL(25, 289, 6), // "groups"
QT_MOC_LITERAL(26, 296, 12), // "groupCreated"
QT_MOC_LITERAL(27, 309, 11), // "groupJoined"
QT_MOC_LITERAL(28, 321, 19), // "createGroupResponse"
QT_MOC_LITERAL(29, 341, 16), // "addGroupResponse"
QT_MOC_LITERAL(30, 358, 27), // "fileTransferRequestReceived"
QT_MOC_LITERAL(31, 386, 8), // "filename"
QT_MOC_LITERAL(32, 395, 8), // "filesize"
QT_MOC_LITERAL(33, 404, 6), // "fileId"
QT_MOC_LITERAL(34, 411, 20), // "fileTransferAccepted"
QT_MOC_LITERAL(35, 432, 8), // "accepted"
QT_MOC_LITERAL(36, 441, 24), // "fileTransferDataReceived"
QT_MOC_LITERAL(37, 466, 10), // "chunkIndex"
QT_MOC_LITERAL(38, 477, 4), // "data"
QT_MOC_LITERAL(39, 482, 28), // "fileTransferCompleteReceived"
QT_MOC_LITERAL(40, 511, 17), // "fileTransferError"
QT_MOC_LITERAL(41, 529, 9), // "errorCode"
QT_MOC_LITERAL(42, 539, 16), // "registerResponse"
QT_MOC_LITERAL(43, 556, 6), // "userId"
QT_MOC_LITERAL(44, 563, 19), // "emojiUploadResponse"
QT_MOC_LITERAL(45, 583, 16), // "emojiListUpdated"
QT_MOC_LITERAL(46, 600, 18), // "QList<QJsonObject>"
QT_MOC_LITERAL(47, 619, 6), // "emojis"
QT_MOC_LITERAL(48, 626, 13), // "avatarUpdated"
QT_MOC_LITERAL(49, 640, 10), // "avatarPath"
QT_MOC_LITERAL(50, 651, 18), // "userAvatarReceived"
QT_MOC_LITERAL(51, 670, 18), // "friendStateUpdated"
QT_MOC_LITERAL(52, 689, 5), // "state"
QT_MOC_LITERAL(53, 695, 11), // "onConnected"
QT_MOC_LITERAL(54, 707, 14), // "onDisconnected"
QT_MOC_LITERAL(55, 722, 11), // "onReadyRead"
QT_MOC_LITERAL(56, 734, 7), // "onError"
QT_MOC_LITERAL(57, 742, 28), // "QAbstractSocket::SocketError"
QT_MOC_LITERAL(58, 771, 11) // "socketError"

    },
    "ChatClient\0connected\0\0disconnected\0"
    "error\0errorMsg\0connectionStateChanged\0"
    "loginResponse\0success\0message\0"
    "messageReceived\0fromId\0fromName\0isGroup\0"
    "groupId\0timestamp\0groupMessageReceived\0"
    "userName\0friendListUpdated\0QList<User>\0"
    "friends\0friendAdded\0addFriendResponse\0"
    "groupListUpdated\0QList<Group>\0groups\0"
    "groupCreated\0groupJoined\0createGroupResponse\0"
    "addGroupResponse\0fileTransferRequestReceived\0"
    "filename\0filesize\0fileId\0fileTransferAccepted\0"
    "accepted\0fileTransferDataReceived\0"
    "chunkIndex\0data\0fileTransferCompleteReceived\0"
    "fileTransferError\0errorCode\0"
    "registerResponse\0userId\0emojiUploadResponse\0"
    "emojiListUpdated\0QList<QJsonObject>\0"
    "emojis\0avatarUpdated\0avatarPath\0"
    "userAvatarReceived\0friendStateUpdated\0"
    "state\0onConnected\0onDisconnected\0"
    "onReadyRead\0onError\0QAbstractSocket::SocketError\0"
    "socketError"
};
#undef QT_MOC_LITERAL

static const uint qt_meta_data_ChatClient[] = {

 // content:
       8,       // revision
       0,       // classname
       0,    0, // classinfo
      35,   14, // methods
       0,    0, // properties
       0,    0, // enums/sets
       0,    0, // constructors
       0,       // flags
      31,       // signalCount

 // signals: name, argc, parameters, tag, flags
       1,    0,  189,    2, 0x06 /* Public */,
       3,    0,  190,    2, 0x06 /* Public */,
       4,    1,  191,    2, 0x06 /* Public */,
       6,    1,  194,    2, 0x06 /* Public */,
       7,    2,  197,    2, 0x06 /* Public */,
      10,    6,  202,    2, 0x06 /* Public */,
      10,    5,  215,    2, 0x26 /* Public | MethodCloned */,
      10,    4,  226,    2, 0x26 /* Public | MethodCloned */,
      10,    3,  235,    2, 0x26 /* Public | MethodCloned */,
      10,    2,  242,    2, 0x26 /* Public | MethodCloned */,
      16,    5,  247,    2, 0x06 /* Public */,
      16,    4,  258,    2, 0x26 /* Public | MethodCloned */,
      18,    1,  267,    2, 0x06 /* Public */,
      21,    2,  270,    2, 0x06 /* Public */,
      22,    2,  275,    2, 0x06 /* Public */,
      23,    1,  280,    2, 0x06 /* Public */,
      26,    2,  283,    2, 0x06 /* Public */,
      27,    2,  288,    2, 0x06 /* Public */,
      28,    2,  293,    2, 0x06 /* Public */,
      29,    2,  298,    2, 0x06 /* Public */,
      30,    4,  303,    2, 0x06 /* Public */,
      34,    2,  312,    2, 0x06 /* Public */,
      36,    3,  317,    2, 0x06 /* Public */,
      39,    2,  324,    2, 0x06 /* Public */,
      40,    3,  329,    2, 0x06 /* Public */,
      42,    3,  336,    2, 0x06 /* Public */,
      44,    2,  343,    2, 0x06 /* Public */,
      45,    1,  348,    2, 0x06 /* Public */,
      48,    1,  351,    2, 0x06 /* Public */,
      50,    1,  354,    2, 0x06 /* Public */,
      51,    2,  357,    2, 0x06 /* Public */,

 // slots: name, argc, parameters, tag, flags
      53,    0,  362,    2, 0x08 /* Private */,
      54,    0,  363,    2, 0x08 /* Private */,
      55,    0,  364,    2, 0x08 /* Private */,
      56,    1,  365,    2, 0x08 /* Private */,

 // signals: parameters
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::QString,    5,
    QMetaType::Void, QMetaType::Bool,    1,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    8,    9,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::QString, QMetaType::Bool, QMetaType::Int, QMetaType::QString,   11,    9,   12,   13,   14,   15,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::QString, QMetaType::Bool, QMetaType::Int,   11,    9,   12,   13,   14,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::QString, QMetaType::Bool,   11,    9,   12,   13,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::QString,   11,    9,   12,
    QMetaType::Void, QMetaType::Int, QMetaType::QString,   11,    9,
    QMetaType::Void, QMetaType::Int, QMetaType::Int, QMetaType::QString, QMetaType::QString, QMetaType::QString,   14,   11,   17,    9,   15,
    QMetaType::Void, QMetaType::Int, QMetaType::Int, QMetaType::QString, QMetaType::QString,   14,   11,   17,    9,
    QMetaType::Void, 0x80000000 | 19,   20,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    8,    9,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    8,    9,
    QMetaType::Void, 0x80000000 | 24,   25,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    8,    9,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    8,    9,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    8,    9,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    8,    9,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::LongLong, QMetaType::QString,   11,   31,   32,   33,
    QMetaType::Void, QMetaType::QString, QMetaType::Bool,   33,   35,
    QMetaType::Void, QMetaType::QString, QMetaType::Int, QMetaType::QByteArray,   33,   37,   38,
    QMetaType::Void, QMetaType::QString, QMetaType::Bool,   33,    8,
    QMetaType::Void, QMetaType::QString, QMetaType::Int, QMetaType::QString,   33,   41,    5,
    QMetaType::Void, QMetaType::Bool, QMetaType::Int, QMetaType::QString,    8,   43,    9,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    8,    9,
    QMetaType::Void, 0x80000000 | 46,   47,
    QMetaType::Void, QMetaType::QString,   49,
    QMetaType::Void, QMetaType::QString,   49,
    QMetaType::Void, QMetaType::LongLong, QMetaType::QString,   43,   52,

 // slots: parameters
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, 0x80000000 | 57,   58,

       0        // eod
};

void ChatClient::qt_static_metacall(QObject *_o, QMetaObject::Call _c, int _id, void **_a)
{
    if (_c == QMetaObject::InvokeMetaMethod) {
        auto *_t = static_cast<ChatClient *>(_o);
        (void)_t;
        switch (_id) {
        case 0: _t->connected(); break;
        case 1: _t->disconnected(); break;
        case 2: _t->error((*reinterpret_cast< const QString(*)>(_a[1]))); break;
        case 3: _t->connectionStateChanged((*reinterpret_cast< bool(*)>(_a[1]))); break;
        case 4: _t->loginResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 5: _t->messageReceived((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< bool(*)>(_a[4])),(*reinterpret_cast< int(*)>(_a[5])),(*reinterpret_cast< const QString(*)>(_a[6]))); break;
        case 6: _t->messageReceived((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< bool(*)>(_a[4])),(*reinterpret_cast< int(*)>(_a[5]))); break;
        case 7: _t->messageReceived((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< bool(*)>(_a[4]))); break;
        case 8: _t->messageReceived((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3]))); break;
        case 9: _t->messageReceived((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 10: _t->groupMessageReceived((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< const QString(*)>(_a[4])),(*reinterpret_cast< const QString(*)>(_a[5]))); break;
        case 11: _t->groupMessageReceived((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< const QString(*)>(_a[4]))); break;
        case 12: _t->friendListUpdated((*reinterpret_cast< const QList<User>(*)>(_a[1]))); break;
        case 13: _t->friendAdded((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 14: _t->addFriendResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 15: _t->groupListUpdated((*reinterpret_cast< const QList<Group>(*)>(_a[1]))); break;
        case 16: _t->groupCreated((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 17: _t->groupJoined((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 18: _t->createGroupResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 19: _t->addGroupResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 20: _t->fileTransferRequestReceived((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< qint64(*)>(_a[3])),(*reinterpret_cast< const QString(*)>(_a[4]))); break;
        case 21: _t->fileTransferAccepted((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< bool(*)>(_a[2]))); break;
        case 22: _t->fileTransferDataReceived((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QByteArray(*)>(_a[3]))); break;
        case 23: _t->fileTransferCompleteReceived((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< bool(*)>(_a[2]))); break;
        case 24: _t->fileTransferError((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3]))); break;
        case 25: _t->registerResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3]))); break;
        case 26: _t->emojiUploadResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 27: _t->emojiListUpdated((*reinterpret_cast< const QList<QJsonObject>(*)>(_a[1]))); break;
        case 28: _t->avatarUpdated((*reinterpret_cast< const QString(*)>(_a[1]))); break;
        case 29: _t->userAvatarReceived((*reinterpret_cast< const QString(*)>(_a[1]))); break;
        case 30: _t->friendStateUpdated((*reinterpret_cast< qint64(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 31: _t->onConnected(); break;
        case 32: _t->onDisconnected(); break;
        case 33: _t->onReadyRead(); break;
        case 34: _t->onError((*reinterpret_cast< QAbstractSocket::SocketError(*)>(_a[1]))); break;
        default: ;
        }
    } else if (_c == QMetaObject::RegisterMethodArgumentMetaType) {
        switch (_id) {
        default: *reinterpret_cast<int*>(_a[0]) = -1; break;
        case 27:
            switch (*reinterpret_cast<int*>(_a[1])) {
            default: *reinterpret_cast<int*>(_a[0]) = -1; break;
            case 0:
                *reinterpret_cast<int*>(_a[0]) = qRegisterMetaType< QList<QJsonObject> >(); break;
            }
            break;
        case 34:
            switch (*reinterpret_cast<int*>(_a[1])) {
            default: *reinterpret_cast<int*>(_a[0]) = -1; break;
            case 0:
                *reinterpret_cast<int*>(_a[0]) = qRegisterMetaType< QAbstractSocket::SocketError >(); break;
            }
            break;
        }
    } else if (_c == QMetaObject::IndexOfMethod) {
        int *result = reinterpret_cast<int *>(_a[0]);
        {
            using _t = void (ChatClient::*)();
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::connected)) {
                *result = 0;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)();
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::disconnected)) {
                *result = 1;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::error)) {
                *result = 2;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(bool );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::connectionStateChanged)) {
                *result = 3;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(bool , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::loginResponse)) {
                *result = 4;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(int , const QString & , const QString & , bool , int , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::messageReceived)) {
                *result = 5;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(int , int , const QString & , const QString & , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::groupMessageReceived)) {
                *result = 10;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(const QList<User> & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::friendListUpdated)) {
                *result = 12;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(bool , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::friendAdded)) {
                *result = 13;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(bool , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::addFriendResponse)) {
                *result = 14;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(const QList<Group> & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::groupListUpdated)) {
                *result = 15;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(bool , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::groupCreated)) {
                *result = 16;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(bool , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::groupJoined)) {
                *result = 17;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(bool , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::createGroupResponse)) {
                *result = 18;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(bool , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::addGroupResponse)) {
                *result = 19;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(int , const QString & , qint64 , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::fileTransferRequestReceived)) {
                *result = 20;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(const QString & , bool );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::fileTransferAccepted)) {
                *result = 21;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(const QString & , int , const QByteArray & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::fileTransferDataReceived)) {
                *result = 22;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(const QString & , bool );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::fileTransferCompleteReceived)) {
                *result = 23;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(const QString & , int , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::fileTransferError)) {
                *result = 24;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(bool , int , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::registerResponse)) {
                *result = 25;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(bool , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::emojiUploadResponse)) {
                *result = 26;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(const QList<QJsonObject> & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::emojiListUpdated)) {
                *result = 27;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::avatarUpdated)) {
                *result = 28;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::userAvatarReceived)) {
                *result = 29;
                return;
            }
        }
        {
            using _t = void (ChatClient::*)(qint64 , const QString & );
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatClient::friendStateUpdated)) {
                *result = 30;
                return;
            }
        }
    }
}

QT_INIT_METAOBJECT const QMetaObject ChatClient::staticMetaObject = { {
    QMetaObject::SuperData::link<QObject::staticMetaObject>(),
    qt_meta_stringdata_ChatClient.data,
    qt_meta_data_ChatClient,
    qt_static_metacall,
    nullptr,
    nullptr
} };


const QMetaObject *ChatClient::metaObject() const
{
    return QObject::d_ptr->metaObject ? QObject::d_ptr->dynamicMetaObject() : &staticMetaObject;
}

void *ChatClient::qt_metacast(const char *_clname)
{
    if (!_clname) return nullptr;
    if (!strcmp(_clname, qt_meta_stringdata_ChatClient.stringdata0))
        return static_cast<void*>(this);
    return QObject::qt_metacast(_clname);
}

int ChatClient::qt_metacall(QMetaObject::Call _c, int _id, void **_a)
{
    _id = QObject::qt_metacall(_c, _id, _a);
    if (_id < 0)
        return _id;
    if (_c == QMetaObject::InvokeMetaMethod) {
        if (_id < 35)
            qt_static_metacall(this, _c, _id, _a);
        _id -= 35;
    } else if (_c == QMetaObject::RegisterMethodArgumentMetaType) {
        if (_id < 35)
            qt_static_metacall(this, _c, _id, _a);
        _id -= 35;
    }
    return _id;
}

// SIGNAL 0
void ChatClient::connected()
{
    QMetaObject::activate(this, &staticMetaObject, 0, nullptr);
}

// SIGNAL 1
void ChatClient::disconnected()
{
    QMetaObject::activate(this, &staticMetaObject, 1, nullptr);
}

// SIGNAL 2
void ChatClient::error(const QString & _t1)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))) };
    QMetaObject::activate(this, &staticMetaObject, 2, _a);
}

// SIGNAL 3
void ChatClient::connectionStateChanged(bool _t1)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))) };
    QMetaObject::activate(this, &staticMetaObject, 3, _a);
}

// SIGNAL 4
void ChatClient::loginResponse(bool _t1, const QString & _t2)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))) };
    QMetaObject::activate(this, &staticMetaObject, 4, _a);
}

// SIGNAL 5
void ChatClient::messageReceived(int _t1, const QString & _t2, const QString & _t3, bool _t4, int _t5, const QString & _t6)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t3))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t4))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t5))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t6))) };
    QMetaObject::activate(this, &staticMetaObject, 5, _a);
}

// SIGNAL 10
void ChatClient::groupMessageReceived(int _t1, int _t2, const QString & _t3, const QString & _t4, const QString & _t5)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t3))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t4))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t5))) };
    QMetaObject::activate(this, &staticMetaObject, 10, _a);
}

// SIGNAL 12
void ChatClient::friendListUpdated(const QList<User> & _t1)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))) };
    QMetaObject::activate(this, &staticMetaObject, 12, _a);
}

// SIGNAL 13
void ChatClient::friendAdded(bool _t1, const QString & _t2)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))) };
    QMetaObject::activate(this, &staticMetaObject, 13, _a);
}

// SIGNAL 14
void ChatClient::addFriendResponse(bool _t1, const QString & _t2)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))) };
    QMetaObject::activate(this, &staticMetaObject, 14, _a);
}

// SIGNAL 15
void ChatClient::groupListUpdated(const QList<Group> & _t1)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))) };
    QMetaObject::activate(this, &staticMetaObject, 15, _a);
}

// SIGNAL 16
void ChatClient::groupCreated(bool _t1, const QString & _t2)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))) };
    QMetaObject::activate(this, &staticMetaObject, 16, _a);
}

// SIGNAL 17
void ChatClient::groupJoined(bool _t1, const QString & _t2)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))) };
    QMetaObject::activate(this, &staticMetaObject, 17, _a);
}

// SIGNAL 18
void ChatClient::createGroupResponse(bool _t1, const QString & _t2)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))) };
    QMetaObject::activate(this, &staticMetaObject, 18, _a);
}

// SIGNAL 19
void ChatClient::addGroupResponse(bool _t1, const QString & _t2)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))) };
    QMetaObject::activate(this, &staticMetaObject, 19, _a);
}

// SIGNAL 20
void ChatClient::fileTransferRequestReceived(int _t1, const QString & _t2, qint64 _t3, const QString & _t4)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t3))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t4))) };
    QMetaObject::activate(this, &staticMetaObject, 20, _a);
}

// SIGNAL 21
void ChatClient::fileTransferAccepted(const QString & _t1, bool _t2)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))) };
    QMetaObject::activate(this, &staticMetaObject, 21, _a);
}

// SIGNAL 22
void ChatClient::fileTransferDataReceived(const QString & _t1, int _t2, const QByteArray & _t3)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t3))) };
    QMetaObject::activate(this, &staticMetaObject, 22, _a);
}

// SIGNAL 23
void ChatClient::fileTransferCompleteReceived(const QString & _t1, bool _t2)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))) };
    QMetaObject::activate(this, &staticMetaObject, 23, _a);
}

// SIGNAL 24
void ChatClient::fileTransferError(const QString & _t1, int _t2, const QString & _t3)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t3))) };
    QMetaObject::activate(this, &staticMetaObject, 24, _a);
}

// SIGNAL 25
void ChatClient::registerResponse(bool _t1, int _t2, const QString & _t3)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t3))) };
    QMetaObject::activate(this, &staticMetaObject, 25, _a);
}

// SIGNAL 26
void ChatClient::emojiUploadResponse(bool _t1, const QString & _t2)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))) };
    QMetaObject::activate(this, &staticMetaObject, 26, _a);
}

// SIGNAL 27
void ChatClient::emojiListUpdated(const QList<QJsonObject> & _t1)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))) };
    QMetaObject::activate(this, &staticMetaObject, 27, _a);
}

// SIGNAL 28
void ChatClient::avatarUpdated(const QString & _t1)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))) };
    QMetaObject::activate(this, &staticMetaObject, 28, _a);
}

// SIGNAL 29
void ChatClient::userAvatarReceived(const QString & _t1)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))) };
    QMetaObject::activate(this, &staticMetaObject, 29, _a);
}

// SIGNAL 30
void ChatClient::friendStateUpdated(qint64 _t1, const QString & _t2)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))), const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t2))) };
    QMetaObject::activate(this, &staticMetaObject, 30, _a);
}
QT_WARNING_POP
QT_END_MOC_NAMESPACE
