# 定义共享源文件
set(SHARED_SOURCES
    chatclient.cpp
    chatclient.h
    chatserver.cpp
    chatserver.h
    public.h
)

# 定义客户端源文件
set(CLIENT_SOURCES
    chatwindow.cpp
    chatwindow.h
    loginwindow.cpp
    loginwindow.h
    main.cpp
    mainwindow.cpp
    mainwindow.h
    messagewidget.cpp
    messagewidget.h
    customtitlebar.cpp
    customtitlebar.h
    farmplotitem.cpp
    farmplotitem.h
    farmdialog.cpp
    farmdialog.h
    qtchat.qrc
)

# 添加子目录
add_subdirectory(server)
add_subdirectory(client)