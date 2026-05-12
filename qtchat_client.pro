QT += core gui network webenginewidgets multimedia websockets

greaterThan(QT_MAJOR_VERSION, 4): QT += widgets

TARGET = QtChatClient
TEMPLATE = app

# 设置C++17标准
CONFIG += c++17

# ==========================================
# 核心修复：解决 Windows 下中文显示为空白/乱码的问题
# ==========================================
# 强制编译器将源文件视为 UTF-8 (解决源码读取问题)
QMAKE_CXXFLAGS += -finput-charset=UTF-8

# 强制编译器生成的二进制字符串也是 UTF-8 (解决运行时显示问题)
QMAKE_CXXFLAGS += -fexec-charset=UTF-8

# 强制 MSVC 编译器将源文件视为 UTF-8，并将执行字符集设为 UTF-8
msvc:QMAKE_CXXFLAGS += /utf-8

# 强制 MinGW / GCC 使用 UTF-8
gcc:QMAKE_CXXFLAGS += -finput-charset=UTF-8 -fexec-charset=UTF-8


# 源文件 - 客户端完整源文件
SOURCES += \
    src/main.cpp \
    src/chatclient.cpp \
    src/chatwindow.cpp \
    src/loginwindow.cpp \
    src/mainwindow.cpp \
    src/messagewidget.cpp \
    src/customtitlebar.cpp \
    src/farmplotitem.cpp \
    src/farmdialog.cpp \
    src/dashboarddialog.cpp \
    src/knowledgegraphdialog.cpp \
    src/realtimevoicedialog.cpp \
    src/companionreadingdialog.cpp \
    src/codingagentdialog.cpp \
    src/chatserver.cpp \
    src/server/db/db.cpp \
    src/server/model/usermodel.cpp \
    src/server/model/friendmodel.cpp \
    src/server/model/groupmodel.cpp \
    src/server/model/offlinemessagemodel.cpp \
    src/server/redis/redis.cpp

# 头文件 - 客户端完整头文件
HEADERS += \
    src/chatclient.h \
    src/chatwindow.h \
    src/loginwindow.h \
    src/mainwindow.h \
    src/public.h \
    src/messagewidget.h \
    src/customtitlebar.h \
    src/farmplotitem.h \
    src/farmdialog.h \
    src/dashboarddialog.h \
    src/knowledgegraphdialog.h \
    src/realtimevoicedialog.h \
    src/companionreadingdialog.h \
    src/codingagentdialog.h \
    src/chatserver.h

# 资源文件
RESOURCES += src/qtchat.qrc

# 包含目录
INCLUDEPATH += $$PWD/src \
               $$PWD/src/server/db \
               $$PWD/src/server/model \
               $$PWD/src/server/redis \
               $$PWD/thirdparty

# 输出目录
DESTDIR = $$PWD/bin

# 目标目录
OBJECTS_DIR = $$PWD/build/obj
MOC_DIR = $$PWD/build/moc
RCC_DIR = $$PWD/build/rcc



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
# 只有在 Debug 模式下才显示黑窗口，Release 模式下自动隐藏
debug {
    CONFIG += console
}
