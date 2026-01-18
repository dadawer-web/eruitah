/****************************************************************************
** Meta object code from reading C++ file 'chatwindow.h'
**
** Created by: The Qt Meta Object Compiler version 67 (Qt 5.15.13)
**
** WARNING! All changes made in this file will be lost!
*****************************************************************************/

#include <memory>
#include "../../../chatwindow.h"
#include <QtCore/qbytearray.h>
#include <QtCore/qmetatype.h>
#include <QtCore/QList>
#if !defined(Q_MOC_OUTPUT_REVISION)
#error "The header file 'chatwindow.h' doesn't include <QObject>."
#elif Q_MOC_OUTPUT_REVISION != 67
#error "This file was generated using the moc from 5.15.13. It"
#error "cannot be used with the include files from this version of Qt."
#error "(The moc has changed too much.)"
#endif

QT_BEGIN_MOC_NAMESPACE
QT_WARNING_PUSH
QT_WARNING_DISABLE_DEPRECATED
struct qt_meta_stringdata_ChatWindow_t {
    QByteArrayData data[60];
    char stringdata0[809];
};
#define QT_MOC_LITERAL(idx, ofs, len) \
    Q_STATIC_BYTE_ARRAY_DATA_HEADER_INITIALIZER_WITH_OFFSET(len, \
    qptrdiff(offsetof(qt_meta_stringdata_ChatWindow_t, stringdata0) + ofs \
        - idx * sizeof(QByteArrayData)) \
    )
static const qt_meta_stringdata_ChatWindow_t qt_meta_stringdata_ChatWindow = {
    {
QT_MOC_LITERAL(0, 0, 10), // "ChatWindow"
QT_MOC_LITERAL(1, 11, 6), // "logout"
QT_MOC_LITERAL(2, 18, 0), // ""
QT_MOC_LITERAL(3, 19, 11), // "onConnected"
QT_MOC_LITERAL(4, 31, 14), // "onDisconnected"
QT_MOC_LITERAL(5, 46, 15), // "onLoginResponse"
QT_MOC_LITERAL(6, 62, 7), // "success"
QT_MOC_LITERAL(7, 70, 8), // "response"
QT_MOC_LITERAL(8, 79, 13), // "onSendMessage"
QT_MOC_LITERAL(9, 93, 11), // "onSendImage"
QT_MOC_LITERAL(10, 105, 11), // "onSendEmoji"
QT_MOC_LITERAL(11, 117, 16), // "onReceiveMessage"
QT_MOC_LITERAL(12, 134, 6), // "fromId"
QT_MOC_LITERAL(13, 141, 7), // "message"
QT_MOC_LITERAL(14, 149, 8), // "fromName"
QT_MOC_LITERAL(15, 158, 7), // "isGroup"
QT_MOC_LITERAL(16, 166, 7), // "groupId"
QT_MOC_LITERAL(17, 174, 9), // "timestamp"
QT_MOC_LITERAL(18, 184, 21), // "onReceiveGroupMessage"
QT_MOC_LITERAL(19, 206, 8), // "userName"
QT_MOC_LITERAL(20, 215, 19), // "onFriendListUpdated"
QT_MOC_LITERAL(21, 235, 11), // "QList<User>"
QT_MOC_LITERAL(22, 247, 7), // "friends"
QT_MOC_LITERAL(23, 255, 18), // "onGroupListUpdated"
QT_MOC_LITERAL(24, 274, 12), // "QList<Group>"
QT_MOC_LITERAL(25, 287, 6), // "groups"
QT_MOC_LITERAL(26, 294, 20), // "onFriendStateUpdated"
QT_MOC_LITERAL(27, 315, 6), // "userId"
QT_MOC_LITERAL(28, 322, 5), // "state"
QT_MOC_LITERAL(29, 328, 11), // "onAddFriend"
QT_MOC_LITERAL(30, 340, 20), // "onAddFriendConfirmed"
QT_MOC_LITERAL(31, 361, 19), // "onAddFriendResponse"
QT_MOC_LITERAL(32, 381, 13), // "onCreateGroup"
QT_MOC_LITERAL(33, 395, 22), // "onCreateGroupConfirmed"
QT_MOC_LITERAL(34, 418, 21), // "onCreateGroupResponse"
QT_MOC_LITERAL(35, 440, 11), // "onJoinGroup"
QT_MOC_LITERAL(36, 452, 20), // "onJoinGroupConfirmed"
QT_MOC_LITERAL(37, 473, 18), // "onAddGroupResponse"
QT_MOC_LITERAL(38, 492, 10), // "onSendFile"
QT_MOC_LITERAL(39, 503, 29), // "onFileTransferRequestReceived"
QT_MOC_LITERAL(40, 533, 8), // "filename"
QT_MOC_LITERAL(41, 542, 8), // "filesize"
QT_MOC_LITERAL(42, 551, 6), // "fileId"
QT_MOC_LITERAL(43, 558, 22), // "onFileTransferAccepted"
QT_MOC_LITERAL(44, 581, 6), // "accept"
QT_MOC_LITERAL(45, 588, 26), // "onFileTransferDataReceived"
QT_MOC_LITERAL(46, 615, 10), // "chunkIndex"
QT_MOC_LITERAL(47, 626, 4), // "data"
QT_MOC_LITERAL(48, 631, 30), // "onFileTransferCompleteReceived"
QT_MOC_LITERAL(49, 662, 19), // "onFileTransferError"
QT_MOC_LITERAL(50, 682, 9), // "errorCode"
QT_MOC_LITERAL(51, 692, 8), // "errorMsg"
QT_MOC_LITERAL(52, 701, 17), // "onContactSelected"
QT_MOC_LITERAL(53, 719, 8), // "onLogout"
QT_MOC_LITERAL(54, 728, 15), // "showContextMenu"
QT_MOC_LITERAL(55, 744, 3), // "pos"
QT_MOC_LITERAL(56, 748, 18), // "onEmojiListUpdated"
QT_MOC_LITERAL(57, 767, 18), // "QList<QJsonObject>"
QT_MOC_LITERAL(58, 786, 6), // "emojis"
QT_MOC_LITERAL(59, 793, 15) // "showEmojiDialog"

    },
    "ChatWindow\0logout\0\0onConnected\0"
    "onDisconnected\0onLoginResponse\0success\0"
    "response\0onSendMessage\0onSendImage\0"
    "onSendEmoji\0onReceiveMessage\0fromId\0"
    "message\0fromName\0isGroup\0groupId\0"
    "timestamp\0onReceiveGroupMessage\0"
    "userName\0onFriendListUpdated\0QList<User>\0"
    "friends\0onGroupListUpdated\0QList<Group>\0"
    "groups\0onFriendStateUpdated\0userId\0"
    "state\0onAddFriend\0onAddFriendConfirmed\0"
    "onAddFriendResponse\0onCreateGroup\0"
    "onCreateGroupConfirmed\0onCreateGroupResponse\0"
    "onJoinGroup\0onJoinGroupConfirmed\0"
    "onAddGroupResponse\0onSendFile\0"
    "onFileTransferRequestReceived\0filename\0"
    "filesize\0fileId\0onFileTransferAccepted\0"
    "accept\0onFileTransferDataReceived\0"
    "chunkIndex\0data\0onFileTransferCompleteReceived\0"
    "onFileTransferError\0errorCode\0errorMsg\0"
    "onContactSelected\0onLogout\0showContextMenu\0"
    "pos\0onEmojiListUpdated\0QList<QJsonObject>\0"
    "emojis\0showEmojiDialog"
};
#undef QT_MOC_LITERAL

static const uint qt_meta_data_ChatWindow[] = {

 // content:
       8,       // revision
       0,       // classname
       0,    0, // classinfo
      37,   14, // methods
       0,    0, // properties
       0,    0, // enums/sets
       0,    0, // constructors
       0,       // flags
       1,       // signalCount

 // signals: name, argc, parameters, tag, flags
       1,    0,  199,    2, 0x06 /* Public */,

 // slots: name, argc, parameters, tag, flags
       3,    0,  200,    2, 0x0a /* Public */,
       4,    0,  201,    2, 0x0a /* Public */,
       5,    2,  202,    2, 0x0a /* Public */,
       8,    0,  207,    2, 0x0a /* Public */,
       9,    0,  208,    2, 0x0a /* Public */,
      10,    0,  209,    2, 0x0a /* Public */,
      11,    6,  210,    2, 0x0a /* Public */,
      11,    5,  223,    2, 0x2a /* Public | MethodCloned */,
      11,    4,  234,    2, 0x2a /* Public | MethodCloned */,
      11,    3,  243,    2, 0x2a /* Public | MethodCloned */,
      11,    2,  250,    2, 0x2a /* Public | MethodCloned */,
      18,    5,  255,    2, 0x0a /* Public */,
      18,    4,  266,    2, 0x2a /* Public | MethodCloned */,
      20,    1,  275,    2, 0x0a /* Public */,
      23,    1,  278,    2, 0x0a /* Public */,
      26,    2,  281,    2, 0x0a /* Public */,
      29,    0,  286,    2, 0x0a /* Public */,
      30,    0,  287,    2, 0x0a /* Public */,
      31,    2,  288,    2, 0x0a /* Public */,
      32,    0,  293,    2, 0x0a /* Public */,
      33,    0,  294,    2, 0x0a /* Public */,
      34,    2,  295,    2, 0x0a /* Public */,
      35,    0,  300,    2, 0x0a /* Public */,
      36,    0,  301,    2, 0x0a /* Public */,
      37,    2,  302,    2, 0x0a /* Public */,
      38,    0,  307,    2, 0x0a /* Public */,
      39,    4,  308,    2, 0x0a /* Public */,
      43,    2,  317,    2, 0x0a /* Public */,
      45,    3,  322,    2, 0x0a /* Public */,
      48,    2,  329,    2, 0x0a /* Public */,
      49,    3,  334,    2, 0x0a /* Public */,
      52,    0,  341,    2, 0x0a /* Public */,
      53,    0,  342,    2, 0x0a /* Public */,
      54,    1,  343,    2, 0x0a /* Public */,
      56,    1,  346,    2, 0x0a /* Public */,
      59,    0,  349,    2, 0x0a /* Public */,

 // signals: parameters
    QMetaType::Void,

 // slots: parameters
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    6,    7,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::QString, QMetaType::Bool, QMetaType::Int, QMetaType::QString,   12,   13,   14,   15,   16,   17,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::QString, QMetaType::Bool, QMetaType::Int,   12,   13,   14,   15,   16,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::QString, QMetaType::Bool,   12,   13,   14,   15,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::QString,   12,   13,   14,
    QMetaType::Void, QMetaType::Int, QMetaType::QString,   12,   13,
    QMetaType::Void, QMetaType::Int, QMetaType::Int, QMetaType::QString, QMetaType::QString, QMetaType::QString,   16,   12,   19,   13,   17,
    QMetaType::Void, QMetaType::Int, QMetaType::Int, QMetaType::QString, QMetaType::QString,   16,   12,   19,   13,
    QMetaType::Void, 0x80000000 | 21,   22,
    QMetaType::Void, 0x80000000 | 24,   25,
    QMetaType::Void, QMetaType::LongLong, QMetaType::QString,   27,   28,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    6,   13,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    6,   13,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    6,   13,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::LongLong, QMetaType::QString,   12,   40,   41,   42,
    QMetaType::Void, QMetaType::QString, QMetaType::Bool,   42,   44,
    QMetaType::Void, QMetaType::QString, QMetaType::Int, QMetaType::QByteArray,   42,   46,   47,
    QMetaType::Void, QMetaType::QString, QMetaType::Bool,   42,    6,
    QMetaType::Void, QMetaType::QString, QMetaType::Int, QMetaType::QString,   42,   50,   51,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::QPoint,   55,
    QMetaType::Void, 0x80000000 | 57,   58,
    QMetaType::Void,

       0        // eod
};

void ChatWindow::qt_static_metacall(QObject *_o, QMetaObject::Call _c, int _id, void **_a)
{
    if (_c == QMetaObject::InvokeMetaMethod) {
        auto *_t = static_cast<ChatWindow *>(_o);
        (void)_t;
        switch (_id) {
        case 0: _t->logout(); break;
        case 1: _t->onConnected(); break;
        case 2: _t->onDisconnected(); break;
        case 3: _t->onLoginResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 4: _t->onSendMessage(); break;
        case 5: _t->onSendImage(); break;
        case 6: _t->onSendEmoji(); break;
        case 7: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< bool(*)>(_a[4])),(*reinterpret_cast< int(*)>(_a[5])),(*reinterpret_cast< const QString(*)>(_a[6]))); break;
        case 8: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< bool(*)>(_a[4])),(*reinterpret_cast< int(*)>(_a[5]))); break;
        case 9: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< bool(*)>(_a[4]))); break;
        case 10: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3]))); break;
        case 11: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 12: _t->onReceiveGroupMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< const QString(*)>(_a[4])),(*reinterpret_cast< const QString(*)>(_a[5]))); break;
        case 13: _t->onReceiveGroupMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< const QString(*)>(_a[4]))); break;
        case 14: _t->onFriendListUpdated((*reinterpret_cast< const QList<User>(*)>(_a[1]))); break;
        case 15: _t->onGroupListUpdated((*reinterpret_cast< const QList<Group>(*)>(_a[1]))); break;
        case 16: _t->onFriendStateUpdated((*reinterpret_cast< qint64(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 17: _t->onAddFriend(); break;
        case 18: _t->onAddFriendConfirmed(); break;
        case 19: _t->onAddFriendResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 20: _t->onCreateGroup(); break;
        case 21: _t->onCreateGroupConfirmed(); break;
        case 22: _t->onCreateGroupResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 23: _t->onJoinGroup(); break;
        case 24: _t->onJoinGroupConfirmed(); break;
        case 25: _t->onAddGroupResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 26: _t->onSendFile(); break;
        case 27: _t->onFileTransferRequestReceived((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< qint64(*)>(_a[3])),(*reinterpret_cast< const QString(*)>(_a[4]))); break;
        case 28: _t->onFileTransferAccepted((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< bool(*)>(_a[2]))); break;
        case 29: _t->onFileTransferDataReceived((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QByteArray(*)>(_a[3]))); break;
        case 30: _t->onFileTransferCompleteReceived((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< bool(*)>(_a[2]))); break;
        case 31: _t->onFileTransferError((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3]))); break;
        case 32: _t->onContactSelected(); break;
        case 33: _t->onLogout(); break;
        case 34: _t->showContextMenu((*reinterpret_cast< const QPoint(*)>(_a[1]))); break;
        case 35: _t->onEmojiListUpdated((*reinterpret_cast< const QList<QJsonObject>(*)>(_a[1]))); break;
        case 36: _t->showEmojiDialog(); break;
        default: ;
        }
    } else if (_c == QMetaObject::RegisterMethodArgumentMetaType) {
        switch (_id) {
        default: *reinterpret_cast<int*>(_a[0]) = -1; break;
        case 35:
            switch (*reinterpret_cast<int*>(_a[1])) {
            default: *reinterpret_cast<int*>(_a[0]) = -1; break;
            case 0:
                *reinterpret_cast<int*>(_a[0]) = qRegisterMetaType< QList<QJsonObject> >(); break;
            }
            break;
        }
    } else if (_c == QMetaObject::IndexOfMethod) {
        int *result = reinterpret_cast<int *>(_a[0]);
        {
            using _t = void (ChatWindow::*)();
            if (*reinterpret_cast<_t *>(_a[1]) == static_cast<_t>(&ChatWindow::logout)) {
                *result = 0;
                return;
            }
        }
    }
}

QT_INIT_METAOBJECT const QMetaObject ChatWindow::staticMetaObject = { {
    QMetaObject::SuperData::link<QMainWindow::staticMetaObject>(),
    qt_meta_stringdata_ChatWindow.data,
    qt_meta_data_ChatWindow,
    qt_static_metacall,
    nullptr,
    nullptr
} };


const QMetaObject *ChatWindow::metaObject() const
{
    return QObject::d_ptr->metaObject ? QObject::d_ptr->dynamicMetaObject() : &staticMetaObject;
}

void *ChatWindow::qt_metacast(const char *_clname)
{
    if (!_clname) return nullptr;
    if (!strcmp(_clname, qt_meta_stringdata_ChatWindow.stringdata0))
        return static_cast<void*>(this);
    return QMainWindow::qt_metacast(_clname);
}

int ChatWindow::qt_metacall(QMetaObject::Call _c, int _id, void **_a)
{
    _id = QMainWindow::qt_metacall(_c, _id, _a);
    if (_id < 0)
        return _id;
    if (_c == QMetaObject::InvokeMetaMethod) {
        if (_id < 37)
            qt_static_metacall(this, _c, _id, _a);
        _id -= 37;
    } else if (_c == QMetaObject::RegisterMethodArgumentMetaType) {
        if (_id < 37)
            qt_static_metacall(this, _c, _id, _a);
        _id -= 37;
    }
    return _id;
}

// SIGNAL 0
void ChatWindow::logout()
{
    QMetaObject::activate(this, &staticMetaObject, 0, nullptr);
}
QT_WARNING_POP
QT_END_MOC_NAMESPACE
