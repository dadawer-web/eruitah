# 配置头文件搜索路径
include_directories(${PROJECT_SOURCE_DIR}/src)
include_directories(${PROJECT_SOURCE_DIR}/src/server/db)
include_directories(${PROJECT_SOURCE_DIR}/src/server/model)
include_directories(${PROJECT_SOURCE_DIR}/src/server/redis)
include_directories(${PROJECT_SOURCE_DIR}/qt-material-widgets/components)
include_directories(${PROJECT_SOURCE_DIR}/qt-material-widgets/components/lib)

# 查找Qt包
find_package(Qt5 COMPONENTS Widgets Network Concurrent Svg WebEngineWidgets Multimedia WebSockets REQUIRED)

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
    ${CMAKE_CURRENT_SOURCE_DIR}/../farmplotitem.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../farmplotitem.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../farmdialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../farmdialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../knowledgegraphdialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../knowledgegraphdialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../realtimevoicedialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../realtimevoicedialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../dashboarddialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../dashboarddialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../companionreadingdialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../companionreadingdialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../codingagentdialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../codingagentdialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../careeradvicepopup.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../careeradvicepopup.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../career_history.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../career_history.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../career_dashboard_dialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../career_dashboard_dialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../career_card_widget.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../desktoppet.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../desktoppet.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../messagebubble.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../messagebubble.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../servicemonitor.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../servicemonitor.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../petmqttclient.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../petmqttclient.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../globaleventbus.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../globaleventbus.h
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
    ${CMAKE_CURRENT_SOURCE_DIR}/../farmplotitem.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../farmplotitem.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../farmdialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../farmdialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../knowledgegraphdialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../knowledgegraphdialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../realtimevoicedialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../realtimevoicedialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../dashboarddialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../dashboarddialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../companionreadingdialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../companionreadingdialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../codingagentdialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../codingagentdialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../careeradvicepopup.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../careeradvicepopup.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../career_history.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../career_history.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../career_dashboard_dialog.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../career_dashboard_dialog.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../career_card_widget.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../desktoppet.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../desktoppet.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../messagebubble.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../messagebubble.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../servicemonitor.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../servicemonitor.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../petmqttclient.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../petmqttclient.h
    ${CMAKE_CURRENT_SOURCE_DIR}/../globaleventbus.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../globaleventbus.h
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
target_link_libraries(ChatClient Qt5::Widgets Qt5::Network Qt5::Concurrent Qt5::Svg Qt5::WebEngineWidgets Qt5::Multimedia Qt5::WebSockets muduo_net muduo_base pthread mysqlclient hiredis mosquitto)
target_link_libraries(QtChat Qt5::Widgets Qt5::Network Qt5::Concurrent Qt5::Svg Qt5::WebEngineWidgets Qt5::Multimedia Qt5::WebSockets muduo_net muduo_base pthread mysqlclient hiredis mosquitto)

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

set(LIVE2D_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../live2d")
set(LIVE2D_DEST_DIR "${CMAKE_CURRENT_BINARY_DIR}/live2d")
set(HTML_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../html")
set(HTML_DEST_DIR "${CMAKE_CURRENT_BINARY_DIR}")

add_custom_command(TARGET QtChat POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "${LIVE2D_DEST_DIR}/hiyori"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${LIVE2D_DEST_DIR}/hiyori/hiyori_pro_t11.2048"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${LIVE2D_DEST_DIR}/hiyori/motion"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${LIVE2D_DEST_DIR}/core"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${LIVE2D_SOURCE_DIR}/hiyori/hiyori_pro_t11.model3.json" "${LIVE2D_DEST_DIR}/hiyori/"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${LIVE2D_SOURCE_DIR}/hiyori/hiyori_pro_t11.moc3" "${LIVE2D_DEST_DIR}/hiyori/"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${LIVE2D_SOURCE_DIR}/hiyori/hiyori_pro_t11.physics3.json" "${LIVE2D_DEST_DIR}/hiyori/"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${LIVE2D_SOURCE_DIR}/hiyori/hiyori_pro_t11.pose3.json" "${LIVE2D_DEST_DIR}/hiyori/"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${LIVE2D_SOURCE_DIR}/hiyori/hiyori_pro_t11.cdi3.json" "${LIVE2D_DEST_DIR}/hiyori/"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${LIVE2D_SOURCE_DIR}/hiyori/hiyori_pro_t11.2048/texture_00.png" "${LIVE2D_DEST_DIR}/hiyori/hiyori_pro_t11.2048/"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${LIVE2D_SOURCE_DIR}/hiyori/hiyori_pro_t11.2048/texture_01.png" "${LIVE2D_DEST_DIR}/hiyori/hiyori_pro_t11.2048/"
    COMMAND ${CMAKE_COMMAND} -E copy_directory "${LIVE2D_SOURCE_DIR}/hiyori/motion" "${LIVE2D_DEST_DIR}/hiyori/motion"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${LIVE2D_SOURCE_DIR}/core/live2dcubismcore.js" "${LIVE2D_DEST_DIR}/core/"
    COMMAND ${CMAKE_COMMAND} -E copy "${HTML_SOURCE_DIR}/avatar.html" "${HTML_DEST_DIR}/"
    COMMAND ${CMAKE_COMMAND} -E copy_directory "${LIVE2D_SOURCE_DIR}/core" "${HTML_DEST_DIR}/live2d/core"
    COMMAND ${CMAKE_COMMAND} -E copy_directory "${LIVE2D_SOURCE_DIR}/hiyori" "${HTML_DEST_DIR}/live2d/hiyori"
    COMMENT "Copying Live2D assets and avatar.html to build directory..."
)
