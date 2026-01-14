QMAKE_MSC_VER = 1900
QMAKE_MSC_FULL_VER = 190024213

QT += core gui network widgets

TARGET = SimpleChatClient
TEMPLATE = app

CONFIG += c++17

SOURCES += \
    src/main.cpp \
    src/chatclient.cpp \
    src/chatwindow.cpp \
    src/loginwindow.cpp \
    src/messagewidget.cpp

HEADERS += \
    src/chatclient.h \
    src/chatwindow.h \
    src/loginwindow.h \
    src/public.h \
    src/messagewidget.h

RESOURCES += src/qtchat.qrc

INCLUDEPATH += $$PWD/src

LIBS += -lws2_32
DEFINES += _WIN32_WINNT=0x0600 UNICODE _UNICODE
# 修复Windows头文件中的byte类型与C++标准库冲突
DEFINES += NOMINMAX
DEFINES += __NO_MINGW_LONGLONG
DEFINES += _HAS_STD_BYTE=0