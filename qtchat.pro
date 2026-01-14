QT += core gui network sql

greaterThan(QT_MAJOR_VERSION, 4): QT += widgets

TARGET = QtChat
TEMPLATE = app

# 设置C++17标准
CONFIG += c++17

# ==========================================
# 核心修复：解决 Windows 下中文显示为空白/乱码的问题
# ==========================================
# 强制 MSVC 编译器将源文件视为 UTF-8，并将执行字符集设为 UTF-8
msvc:QMAKE_CXXFLAGS += /utf-8

# 强制 MinGW / GCC 使用 UTF-8
gcc:QMAKE_CXXFLAGS += -finput-charset=UTF-8 -fexec-charset=UTF-8

# 源文件
SOURCES += \
    src/main.cpp \
    src/chatclient.cpp \
    src/chatserver.cpp \
    src/chatwindow.cpp \
    src/loginwindow.cpp \
    src/models/usermodel.cpp \
    src/models/friendmodel.cpp \
    src/models/groupmodel.cpp \
    src/models/offlinemessagemodel.cpp \
    src/db/db.cpp

# 头文件
HEADERS += \
    src/chatclient.h \
    src/chatserver.h \
    src/chatwindow.h \
    src/loginwindow.h \
    src/models/user.h \
    src/models/group.h \
    src/models/groupuser.h \
    src/models/usermodel.h \
    src/models/friendmodel.h \
    src/models/groupmodel.h \
    src/models/offlinemessagemodel.h \
    src/db/db.h \
    src/public.h

# 资源文件
RESOURCES += src/qtchat.qrc

# 包含目录
INCLUDEPATH += $$PWD/src \
               $$PWD/thirdparty

# 链接MySQL库
LIBS += -lmysqlclient -lcrypto -lssl

# 输出目录
DESTDIR = $$PWD/bin

# 目标目录
OBJECTS_DIR = $$PWD/build/obj
MOC_DIR = $$PWD/build/moc
RCC_DIR = $$PWD/build/rcc