QT += core gui network

greaterThan(QT_MAJOR_VERSION, 4): QT += widgets

TARGET = QtChatClient
TEMPLATE = app

# 设置C++17标准
CONFIG += c++17



# 源文件 - 只包含客户端相关文件
SOURCES += \
    src/main.cpp \
    src/chatclient.cpp \
    src/chatwindow.cpp \
    src/loginwindow.cpp \
    src/messagewidget.cpp

# 头文件 - 只包含客户端相关文件
HEADERS += \
    src/chatclient.h \
    src/chatwindow.h \
    src/loginwindow.h \
    src/public.h \
    src/messagewidget.h

# 资源文件
RESOURCES += src/qtchat.qrc

# 包含目录
INCLUDEPATH += $$PWD/src \
               $$PWD/thirdparty

# 输出目录
DESTDIR = $$PWD/bin

# 目标目录
OBJECTS_DIR = $$PWD/build/obj
MOC_DIR = $$PWD/build/moc
RCC_DIR = $$PWD/build/rcc

# 修复MSVC版本检测问题
QMAKE_MSC_VER = 1900
QMAKE_MSC_FULL_VER = 190024213

# 跨平台编译配置
win32 {
    # Windows 特定配置
    LIBS += -lws2_32
    DEFINES += _WIN32_WINNT=0x0600
    # 确保Windows平台正确处理Unicode
    DEFINES += UNICODE _UNICODE
    # 修复Windows头文件中的byte类型与C++标准库冲突
    DEFINES += NOMINMAX
    DEFINES += __NO_MINGW_LONGLONG
    DEFINES += NO_SYS_TYPES_H
    DEFINES += _CRT_SECURE_NO_WARNINGS
    DEFINES += _CRT_NONSTDC_NO_WARNINGS
    # 确保std::byte可用
    DEFINES += _HAS_STD_BYTE=1
} else {
    # Linux 特定配置
    LIBS += -lcrypto -lssl
}

# 通用配置
CONFIG += console
