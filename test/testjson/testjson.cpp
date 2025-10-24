#include"json.hpp"
using json=nlohmann::json;
#include<iostream>
#include<vector>
#include<map>
#include<string>
using namespace std;
//json1
void func1(){
    json js;//一个json对象
    js["msg_type"]=2;
    js["from"]="zhangsan";
    js["to"]="li si";
    js["msg"]="hello,what are you doing now?";
    string sendBuf=js.dump();
    cout<<sendBuf.c_str()<<endl;//利用网络发送
    //cout<<js<<endl;
}
//输出{"from":"zhangsan","msg":"hello,what are you doing now?","msg_type":2,"to":"li si"}是无序的，底层是链式哈希表
//json2
void func2(){
    json js;
    // 添加数组
    js["id"] = {1,2,3,4,5}; 
    // 添加key-value
    js["name"] = "zhang san"; 
    // 添加对象
    js["msg"]["zhang san"] = "hello world";
    js["msg"]["liu shuo"] = "hello china"; 
    // 上面等同于下面这句一次性添加数组对象
    js["msg"] = {{"zhang san", "hello world"}, {"liu shuo", "hello china"}};
    cout << js << endl;
}
//{"id":[1,2,3,4,5],"msg":{"liu shuo":"hello china","zhang san":"hello world"},"name":"zhang san"}
//json3
void func3(){
    json js;
    // 直接序列化一个vector容器
    vector<int> vec;
    vec.push_back(1);
    vec.push_back(2);
    vec.push_back(5);
    js["list"] = vec;
    // 直接序列化一个map容器
    map<int, string> m;
    m.insert({1, "黄山"});
    m.insert({2, "华山"});
    m.insert({3, "泰山"});
    js["path"] = m;
    string sendBuf = js.dump();//json数据对象=>序列化 json字符串 传送到网络
    cout << sendBuf << endl;
}
//{"list":[1,2,5],"path":[[1,"黄山"],[2,"华山"],[3,"泰山"]]}
int main(){
    //func1();
    //func2();
    func3();
    return 0;
}