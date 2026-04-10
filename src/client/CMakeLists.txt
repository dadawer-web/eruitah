# 配置头文件搜索路径
include_directories(${PROJECT_SOURCE_DIR}/src)
include_directories(${PROJECT_SOURCE_DIR}/src/server/db)
include_directories(${PROJECT_SOURCE_DIR}/src/server/model)
include_directories(${PROJECT_SOURCE_DIR}/src/server/redis)
include_directories(${PROJECT_SOURCE_DIR}/qt-material-widgets/components)
include_directories(${PROJECT_SOURCE_DIR}/qt-material-widgets/components/lib)

# 查找Qt包
find_package(Qt5 COMPONENTS Widgets Network Concurrent Svg REQUIRED)

# 设置muduo路径（如果客户端需要用到）
set(MUDUO_ROOT_DIR "/home/xmy/muduo")
include_directories(${MUDUO_ROOT_DIR}/include)
link_directories(${MUDUO_ROOT_DIR}/build/lib)

# Qt Material Widgets 源文件
set(MATERIAL_SOURCES
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialavatar.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/lib/qtmaterialstyle.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/lib/qtmaterialtheme.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/lib/qtmaterialoverlaywidget.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/lib/qtmaterialripple.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/lib/qtmaterialrippleoverlay.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/lib/qtmaterialcheckable.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/lib/qtmaterialcheckable_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/lib/qtmaterialstatetransition.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialbadge.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialcheckbox.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialfab.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialraisedbutton.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialflatbutton.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialflatbutton_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialiconbutton.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialprogress.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialprogress_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialcircularprogress.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialcircularprogress_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialslider.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialslider_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialsnackbar.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialsnackbar_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialradiobutton.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialtoggle.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialtoggle_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialtextfield.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialtextfield_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialtabs.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialtabs_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialscrollbar.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialscrollbar_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialdialog.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialdialog_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialdrawer.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialdrawer_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialappbar.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialautocomplete.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialautocomplete_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialpaper.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialtable.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/layouts/qtmaterialsnackbarlayout.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialmenu.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmaterialmenu_internal.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmateriallist.cpp
    ${PROJECT_SOURCE_DIR}/qt-material-widgets/components/qtmateriallistitem.cpp
)

# 定义客户端源文件列表
set(CLIENT_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatclient.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatwindow.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../loginwindow.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../mainwindow.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatserver.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../public.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatclient.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatwindow.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../loginwindow.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../mainwindow.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatserver.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../messagewidget.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../messagewidget.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../customtitlebar.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../customtitlebar.h
    # 服务器相关的核心文件（为了支持MainWindow中的服务器功能）
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/db/db.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/model/usermodel.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/model/friendmodel.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/model/groupmodel.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/model/offlinemessagemodel.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/redis/redis.cpp
)

# 定义QtChat源文件列表（使用Qt图形界面版本的main.cpp）
set(QT_CHAT_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/../main.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatclient.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatwindow.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../loginwindow.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../mainwindow.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatserver.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../public.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatclient.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatwindow.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../loginwindow.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../mainwindow.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../chatserver.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../messagewidget.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../messagewidget.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../customtitlebar.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../customtitlebar.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../qtchat.qrc
    # 服务器相关的核心文件
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/db/db.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/model/usermodel.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/model/friendmodel.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/model/groupmodel.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/model/offlinemessagemodel.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../server/redis/redis.cpp
)

# 指定生成命令行版本可执行文件
add_executable(ChatClient ${CLIENT_SOURCES} ${MATERIAL_SOURCES})

# 指定生成Qt图形界面版本可执行文件
add_executable(QtChat ${QT_CHAT_SOURCES} ${MATERIAL_SOURCES})

# 指定可执行文件所依赖的库
target_link_libraries(ChatClient Qt5::Widgets Qt5::Network Qt5::Concurrent Qt5::Svg muduo_net muduo_base pthread mysqlclient hiredis)
target_link_libraries(QtChat Qt5::Widgets Qt5::Network Qt5::Concurrent Qt5::Svg muduo_net muduo_base pthread mysqlclient hiredis)

# 启用Qt的MOC处理
set_target_properties(ChatClient PROPERTIES
    AUTOMOC ON
    AUTORCC ON
    AUTOUIC ON
)
set_target_properties(QtChat PROPERTIES
    AUTOMOC ON
    AUTORCC ON
    AUTOUIC ON
)
