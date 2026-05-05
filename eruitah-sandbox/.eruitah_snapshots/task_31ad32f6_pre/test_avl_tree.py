#!/usr/bin/env python3
"""
平衡二叉树测试文件
"""

from avl_tree import AVLTree

def test_insertion():
    """测试插入功能"""
    print("=== 测试插入功能 ===")
    avl = AVLTree()
    
    # 插入一些测试数据
    keys = [10, 20, 30, 40, 50, 25]
    for key in keys:
        avl.insert_key(key)
        print(f"插入 {key} 后，中序遍历: {avl.get_inorder()}")

def test_deletion():
    """测试删除功能"""
    print("\n=== 测试删除功能 ===")
    avl = AVLTree()
    
    # 插入测试数据
    keys = [9, 5, 10, 0, 6, 11, -1, 1, 2]
    for key in keys:
        avl.insert_key(key)
    
    print(f"插入所有键后，中序遍历: {avl.get_inorder()}")
    print(f"前序遍历: {avl.get_preorder()}")
    
    # 删除一些键
    avl.delete_key(10)
    print(f"删除 10 后，中序遍历: {avl.get_inorder()}")
    print(f"前序遍历: {avl.get_preorder()}")

def test_search():
    """测试搜索功能"""
    print("\n=== 测试搜索功能 ===")
    avl = AVLTree()
    
    # 插入测试数据
    keys = [10, 20, 30, 5, 15]
    for key in keys:
        avl.insert_key(key)
    
    # 测试搜索
    search_keys = [10, 5, 25, 15]
    for key in search_keys:
        result = avl.search_key(key)
        if result:
            print(f"找到键 {key}")
        else:
            print(f"未找到键 {key}")

def test_tree_structure():
    """测试树结构显示"""
    print("\n=== 测试树结构显示 ===")
    avl = AVLTree()
    
    # 插入测试数据
    keys = [50, 30, 70, 20, 40, 60, 80]
    for key in keys:
        avl.insert_key(key)
    
    print("树结构:")
    avl.display()
    
    print(f"\n中序遍历: {avl.get_inorder()}")
    print(f"前序遍历: {avl.get_preorder()}")
    print(f"后序遍历: {avl.get_postorder()}")

def test_avl_balance():
    """测试AVL树的平衡性"""
    print("\n=== 测试AVL树平衡性 ===")
    avl = AVLTree()
    
    # 插入数据，测试树的平衡
    keys = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    for key in keys:
        avl.insert_key(key)
        print(f"插入 {key} 后，树高度: {avl.root.height if avl.root else 0}")
    
    print(f"最终中序遍历: {avl.get_inorder()}")
    print("最终树结构:")
    avl.display()

if __name__ == "__main__":
    # 运行所有测试
    test_insertion()
    test_deletion()
    test_search()
    test_tree_structure()
    test_avl_balance()
    
    print("\n=== 所有测试完成 ===")