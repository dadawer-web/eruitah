/****************************************************************************
** Meta object code from reading C++ file 'chatwindow.h'
**
** Created by: The Qt Meta Object Compiler version 67 (Qt 5.15.13)
**
** WARNING! All changes made in this file will be lost!
*****************************************************************************/

#include <memory>
#include "../../../../../src/chatwindow.h"
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
    QByteArrayData data[50];
    char stringdata0[680];
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
QT_MOC_LITERAL(12, 125, 8), // "fromName"
QT_MOC_LITERAL(13, 134, 7), // "isGroup"
QT_MOC_LITERAL(14, 142, 7), // "groupId"
QT_MOC_LITERAL(15, 150, 21), // "onReceiveGroupMessage"
QT_MOC_LITERAL(16, 172, 8), // "userName"
QT_MOC_LITERAL(17, 181, 19), // "onFriendListUpdated"
QT_MOC_LITERAL(18, 201, 11), // "QList<User>"
QT_MOC_LITERAL(19, 213, 7), // "friends"
QT_MOC_LITERAL(20, 221, 18), // "onGroupListUpdated"
QT_MOC_LITERAL(21, 240, 12), // "QList<Group>"
QT_MOC_LITERAL(22, 253, 6), // "groups"
QT_MOC_LITERAL(23, 260, 11), // "onAddFriend"
QT_MOC_LITERAL(24, 272, 20), // "onAddFriendConfirmed"
QT_MOC_LITERAL(25, 293, 19), // "onAddFriendResponse"
QT_MOC_LITERAL(26, 313, 13), // "onCreateGroup"
QT_MOC_LITERAL(27, 327, 22), // "onCreateGroupConfirmed"
QT_MOC_LITERAL(28, 350, 21), // "onCreateGroupResponse"
QT_MOC_LITERAL(29, 372, 11), // "onJoinGroup"
QT_MOC_LITERAL(30, 384, 20), // "onJoinGroupConfirmed"
QT_MOC_LITERAL(31, 405, 18), // "onAddGroupResponse"
QT_MOC_LITERAL(32, 424, 10), // "onSendFile"
QT_MOC_LITERAL(33, 435, 29), // "onFileTransferRequestReceived"
QT_MOC_LITERAL(34, 465, 8), // "filename"
QT_MOC_LITERAL(35, 474, 8), // "filesize"
QT_MOC_LITERAL(36, 483, 6), // "fileId"
QT_MOC_LITERAL(37, 490, 22), // "onFileTransferAccepted"
QT_MOC_LITERAL(38, 513, 6), // "accept"
QT_MOC_LITERAL(39, 520, 26), // "onFileTransferDataReceived"
QT_MOC_LITERAL(40, 547, 10), // "chunkIndex"
QT_MOC_LITERAL(41, 558, 4), // "data"
QT_MOC_LITERAL(42, 563, 30), // "onFileTransferCompleteReceived"
QT_MOC_LITERAL(43, 594, 19), // "onFileTransferError"
QT_MOC_LITERAL(44, 614, 9), // "errorCode"
QT_MOC_LITERAL(45, 624, 8), // "errorMsg"
QT_MOC_LITERAL(46, 633, 17), // "onContactSelected"
QT_MOC_LITERAL(47, 651, 8), // "onLogout"
QT_MOC_LITERAL(48, 660, 15), // "showContextMenu"
QT_MOC_LITERAL(49, 676, 3) // "pos"

    },
    "ChatWindow\0logout\0\0onConnected\0"
    "onDisconnected\0onLoginResponse\0success\0"
    "response\0onSendMessage\0onReceiveMessage\0"
    "fromId\0message\0fromName\0isGroup\0groupId\0"
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
      30,   14, // methods
       0,    0, // properties
       0,    0, // enums/sets
       0,    0, // constructors
       0,       // flags
       1,       // signalCount

 // signals: name, argc, parameters, tag, flags
       1,    0,  164,    2, 0x06 /* Public */,

 // slots: name, argc, parameters, tag, flags
       3,    0,  165,    2, 0x0a /* Public */,
       4,    0,  166,    2, 0x0a /* Public */,
       5,    2,  167,    2, 0x0a /* Public */,
       8,    0,  172,    2, 0x0a /* Public */,
       9,    5,  173,    2, 0x0a /* Public */,
       9,    4,  184,    2, 0x2a /* Public | MethodCloned */,
       9,    3,  193,    2, 0x2a /* Public | MethodCloned */,
       9,    2,  200,    2, 0x2a /* Public | MethodCloned */,
      15,    4,  205,    2, 0x0a /* Public */,
      17,    1,  214,    2, 0x0a /* Public */,
      20,    1,  217,    2, 0x0a /* Public */,
      23,    0,  220,    2, 0x0a /* Public */,
      24,    0,  221,    2, 0x0a /* Public */,
      25,    2,  222,    2, 0x0a /* Public */,
      26,    0,  227,    2, 0x0a /* Public */,
      27,    0,  228,    2, 0x0a /* Public */,
      28,    2,  229,    2, 0x0a /* Public */,
      29,    0,  234,    2, 0x0a /* Public */,
      30,    0,  235,    2, 0x0a /* Public */,
      31,    2,  236,    2, 0x0a /* Public */,
      32,    0,  241,    2, 0x0a /* Public */,
      33,    4,  242,    2, 0x0a /* Public */,
      37,    2,  251,    2, 0x0a /* Public */,
      39,    3,  256,    2, 0x0a /* Public */,
      42,    2,  263,    2, 0x0a /* Public */,
      43,    3,  268,    2, 0x0a /* Public */,
      46,    0,  275,    2, 0x0a /* Public */,
      47,    0,  276,    2, 0x0a /* Public */,
      48,    1,  277,    2, 0x0a /* Public */,

 // signals: parameters
    QMetaType::Void,

 // slots: parameters
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Bool, QMetaType::QString,    6,    7,
    QMetaType::Void,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::QString, QMetaType::Bool, QMetaType::Int,   10,   11,   12,   13,   14,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::QString, QMetaType::Bool,   10,   11,   12,   13,
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::QString,   10,   11,   12,
    QMetaType::Void, QMetaType::Int, QMetaType::QString,   10,   11,
    QMetaType::Void, QMetaType::Int, QMetaType::Int, QMetaType::QString, QMetaType::QString,   14,   10,   16,   11,
    QMetaType::Void, 0x80000000 | 18,   19,
    QMetaType::Void, 0x80000000 | 21,   22,
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
    QMetaType::Void, QMetaType::Int, QMetaType::QString, QMetaType::LongLong, QMetaType::QString,   10,   34,   35,   36,
    QMetaType::Void, QMetaType::QString, QMetaType::Bool,   36,   38,
    QMetaType::Void, QMetaType::QString, QMetaType::Int, QMetaType::QByteArray,   36,   40,   41,
    QMetaType::Void, QMetaType::QString, QMetaType::Bool,   36,    6,
    QMetaType::Void, QMetaType::QString, QMetaType::Int, QMetaType::QString,   36,   44,   45,
    QMetaType::Void,
    QMetaType::Void,
    QMetaType::Void, QMetaType::QPoint,   49,

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
        case 5: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< bool(*)>(_a[4])),(*reinterpret_cast< int(*)>(_a[5]))); break;
        case 6: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< bool(*)>(_a[4]))); break;
        case 7: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3]))); break;
        case 8: _t->onReceiveMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 9: _t->onReceiveGroupMessage((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3])),(*reinterpret_cast< const QString(*)>(_a[4]))); break;
        case 10: _t->onFriendListUpdated((*reinterpret_cast< const QList<User>(*)>(_a[1]))); break;
        case 11: _t->onGroupListUpdated((*reinterpret_cast< const QList<Group>(*)>(_a[1]))); break;
        case 12: _t->onAddFriend(); break;
        case 13: _t->onAddFriendConfirmed(); break;
        case 14: _t->onAddFriendResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 15: _t->onCreateGroup(); break;
        case 16: _t->onCreateGroupConfirmed(); break;
        case 17: _t->onCreateGroupResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 18: _t->onJoinGroup(); break;
        case 19: _t->onJoinGroupConfirmed(); break;
        case 20: _t->onAddGroupResponse((*reinterpret_cast< bool(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2]))); break;
        case 21: _t->onSendFile(); break;
        case 22: _t->onFileTransferRequestReceived((*reinterpret_cast< int(*)>(_a[1])),(*reinterpret_cast< const QString(*)>(_a[2])),(*reinterpret_cast< qint64(*)>(_a[3])),(*reinterpret_cast< const QString(*)>(_a[4]))); break;
        case 23: _t->onFileTransferAccepted((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< bool(*)>(_a[2]))); break;
        case 24: _t->onFileTransferDataReceived((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QByteArray(*)>(_a[3]))); break;
        case 25: _t->onFileTransferCompleteReceived((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< bool(*)>(_a[2]))); break;
        case 26: _t->onFileTransferError((*reinterpret_cast< const QString(*)>(_a[1])),(*reinterpret_cast< int(*)>(_a[2])),(*reinterpret_cast< const QString(*)>(_a[3]))); break;
        case 27: _t->onContactSelected(); break;
        case 28: _t->onLogout(); break;
        case 29: _t->showContextMenu((*reinterpret_cast< const QPoint(*)>(_a[1]))); break;
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
        if (_id < 30)
            qt_static_metacall(this, _c, _id, _a);
        _id -= 30;
    } else if (_c == QMetaObject::RegisterMethodArgumentMetaType) {
        if (_id < 30)
            *reinterpret_cast<int*>(_a[0]) = -1;
        _id -= 30;
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
