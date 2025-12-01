/****************************************************************************
** Meta object code from reading C++ file 'chatwindow.h'
**
** Created by: The Qt Meta Object Compiler version 67 (Qt 5.15.13)
**
** WARNING! All changes made in this file will be lost!
*****************************************************************************/

#include <memory>
#include "../../src/chatwindow.h"
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
    QByteArrayData data[49];
    char stringdata0[671];
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
QT_MOC_LITERAL(9, 93, 16), // "onReceiveMessage"
QT_MOC_LITERAL(10, 110, 6), // "fromId"
QT_MOC_LITERAL(11, 117, 7), // "message"
QT_MOC_LITERAL(12, 125, 7), // "isGroup"
QT_MOC_LITERAL(13, 133, 7), // "groupId"
QT_MOC_LITERAL(14, 141, 21), // "onReceiveGroupMessage"
QT_MOC_LITERAL(15, 163, 8), // "userName"
QT_MOC_LITERAL(16, 172, 19), // "onFriendListUpdated"
QT_MOC_LITERAL(17, 192, 11), // "QList<User>"
QT_MOC_LITERAL(18, 204, 7), // "friends"
QT_MOC_LITERAL(19, 212, 18), // "onGroupListUpdated"
QT_MOC_LITERAL(20, 231, 12), // "QList<Group>"
QT_MOC_LITERAL(21, 244, 6), // "groups"
QT_MOC_LITERAL(22, 251, 11), // "onAddFriend"
QT_MOC_LITERAL(23, 263, 20), // "onAddFriendConfirmed"
QT_MOC_LITERAL(24, 284, 19), // "onAddFriendResponse"
QT_MOC_LITERAL(25, 304, 13), // "onCreateGroup"
QT_MOC_LITERAL(26, 318, 22), // "onCreateGroupConfirmed"
QT_MOC_LITERAL(27, 341, 21), // "onCreateGroupResponse"
QT_MOC_LITERAL(28, 363, 11), // "onJoinGroup"
QT_MOC_LITERAL(29, 375, 20), // "onJoinGroupConfirmed"
QT_MOC_LITERAL(30, 396, 18), // "onAddGroupResponse"
QT_MOC_LITERAL(31, 415, 10), // "onSendFile"
QT_MOC_LITERAL(32, 426, 29), // "onFileTransferRequestReceived"
QT_MOC_LITERAL(33, 456, 8), // "filename"
QT_MOC_LITERAL(34, 465, 8), // "filesize"
QT_MOC_LITERAL(35, 474, 6), // "fileId"
QT_MOC_LITERAL(36, 481, 22), // "onFileTransferAccepted"
QT_MOC_LITERAL(37, 504, 6), // "accept"
QT_MOC_LITERAL(38, 511, 26), // "onFileTransferDataReceived"
QT_MOC_LITERAL(39, 538, 10), // "chunkIndex"
QT_MOC_LITERAL(40, 549, 4), // "data"
QT_MOC_LITERAL(41, 554, 30), // "onFileTransferCompleteReceived"
QT_MOC_LITERAL(42, 585, 19), // "onFileTransferError"
QT_MOC_LITERAL(43, 605, 9), // "errorCode"
QT_MOC_LITERAL(44, 615, 8), // "errorMsg"
QT_MOC_LITERAL(45, 624, 17), // "onContactSelected"
QT_MOC_LITERAL(46, 642, 8), // "onLogout"
QT_MOC_LITERAL(47, 651, 15), // "showContextMenu"
QT_MOC_LITERAL(48, 667, 3) // "pos"

    },
    "ChatWindow\0logout\0\0onConnected\0"
    "onDisconnected\0onLoginResponse\0success\0"
    "response\0onSendMessage\0onReceiveMessage\0"
    "fromId\0message\0isGroup\0groupId\0"
    "onReceiveGroupMessage\0userName\0"
    "onFriendListUpdated\0QList<User>\0friends\0"
    "onGroupListUpdated\0QList<Group>\0groups\0"
    "onAddFriend\0onAddFriendConfirmed\0"
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
    "pos"
};
#undef QT_MOC_LITERAL

static const uint qt_meta_data_ChatWindow[] = {

 // content:
       8,       // revision
       0,       // classname
       0,    0, // classinfo
      29,   14, // methods
       0,    0, // properties
       0,    0, // enums/sets
       0,    0, // constructors
       0,       // flags
       1,       // signalCount

 // signals: name, argc, parameters, tag, flags
       1,    0,  159,    2, 0x06 /* Public */,

 // slots: name, argc, parameters, tag, flags
       3,    0,  160,    2, 0x0a /* Public */,
       4,    0,  161,    2, 0x0a /* Public */,
       5,    2,  162,    2, 0x0a /* Public */,
       8,    0,  167,    2, 0x0a /* Public */,
       9,    4,  168,    2, 0x0a /* Public */,
       9,    3,  177,    2, 0x2a /* Public | MethodCloned */,
       9,    2,  184,    2, 0x2a /* Public | MethodCloned */,
      14,    4,  189,    2, 0x0a /* Public */,
      16,    1,  198,    2, 0x0a /* Public */,
      19,    1,  201,    2, 0x0a /* Public */,
      22,    0,  204,    2, 0x0a /* Public */,
      23,    0,  205,    2, 0x0a /* Public */,
      24,    2,  206,    2, 0x0a /* Public */,
      25,    0,  211,    2, 0x0a /* Public */,
      26,    0,  212,    2, 0x0a /* Public */,
      27,    2,  213,    2, 0x0a /* Public */,
      28,    0,  218,    2, 0x0a /* Public */,
      29,    0,  219,    2, 0x0a /* Public */,
      30,    2,  220,    2, 0x0a /* Public */,
      31,    0,  225,    2, 0x0a /* Public */,
      32,    4,  226,    2, 0x0a /* Public */,
      36,    2,  235,    2, 0x0a /* Public */,
      38,    3,  240,    2, 0x0a /* Public */,
      41,    2,  247,    2, 0x0a /* Public */,
      42,    3,  252,    2, 0x0a /* Public */,
      45,    0,  259,    2, 0x0a /* Public */,
      46,    0,  260,    2, 0x0a /* Public */,
      47,    1,  261,    2, 0x0a /* Public */,

 // signals: parameters
    QMetaType::Void,

 // slots: parameters
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    6,    7,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::Bool, QMetaType::Int,   10,   11,   12,   13,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::Bool,   10,   11,   12,
    QMetaType::Void, QMetaType::Int, QMetaType::QString,   10,   11,
    QMetaType::Void, QMetaType::Int, QMetaType::Int, QMetaType::QString, QMetaType::QString,   13,   10,   15,   11,
    QMetaType::Void, 0x80000000 | 17,   18,
    QMetaType::Void, 0x80000000 | 20,   21,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    6,   11,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    6,   11,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    6,   11,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::LongLong, QMetaType::QString,   10,   33,   34,   35,
    QMetaType::Void, QMetaType::QString, QMetaType::Bool,   35,   37,
    QMetaType::Void, QMetaType::QString, QMetaType::Int, QMetaType::QByteArray,   35,   39,   40,
    QMetaType::Void, QMetaType::QString, QMetaType::Bool,   35,    6,
    QMetaType::Void, QMetaType::QString, QMetaType::Int, QMetaType::QString,   35,   43,   44,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::QPoint,   48,

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
        case 5: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< bool(*)>(_a[3])),(*reinterpret_cast< int(*)>(_a[4]))); break;
        case 6: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< bool(*)>(_a[3]))); break;
        case 7: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 8: _t->onReceiveGroupMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< const QString(*)>(_a[4]))); break;
        case 9: _t->onFriendListUpdated((*reinterpret_cast< const QList<User>(*)>(_a[1]))); break;
        case 10: _t->onGroupListUpdated((*reinterpret_cast< const QList<Group>(*)>(_a[1]))); break;
        case 11: _t->onAddFriend(); break;
        case 12: _t->onAddFriendConfirmed(); break;
        case 13: _t->onAddFriendResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 14: _t->onCreateGroup(); break;
        case 15: _t->onCreateGroupConfirmed(); break;
        case 16: _t->onCreateGroupResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 17: _t->onJoinGroup(); break;
        case 18: _t->onJoinGroupConfirmed(); break;
        case 19: _t->onAddGroupResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 20: _t->onSendFile(); break;
        case 21: _t->onFileTransferRequestReceived((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< qint64(*)>(_a[3])),(*reinterpret_cast< const QString(*)>(_a[4]))); break;
        case 22: _t->onFileTransferAccepted((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< bool(*)>(_a[2]))); break;
        case 23: _t->onFileTransferDataReceived((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QByteArray(*)>(_a[3]))); break;
        case 24: _t->onFileTransferCompleteReceived((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< bool(*)>(_a[2]))); break;
        case 25: _t->onFileTransferError((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3]))); break;
        case 26: _t->onContactSelected(); break;
        case 27: _t->onLogout(); break;
        case 28: _t->showContextMenu((*reinterpret_cast< const QPoint(*)>(_a[1]))); break;
        default: ;
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
        if (_id < 29)
            qt_static_metacall(this, _c, _id, _a);
        _id -= 29;
    } else if (_c == QMetaObject::RegisterMethodArgumentMetaType) {
        if (_id < 29)
            *reinterpret_cast<int*>(_a[0]) = -1;
        _id -= 29;
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
