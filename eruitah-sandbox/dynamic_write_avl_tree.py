def write_avl_tree_file():
    content = '''"""
平衡二叉树（AVL树）实现
AVL树是一种自平衡的二叉搜索树，任何节点的两个子树的高度最多相差1
"""

class AVLNode:
    """AVL树节点类"""
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None
        self.height = 1  # 节点高度
        self.balance_factor = 0  # 平衡因子


class AVLTree:
    """AVL树类"""
    
    def __init__(self):
        self.root = None
    
    def get_height(self, node):
        """获取节点高度"""
        if node is None:
            return 0
        return node.height
    
    def get_balance_factor(self, node):
        """获取节点的平衡因子"""
        if node is None:
            return 0
        return self.get_height(node.left) - self.get_height(node.right)
    
    def update_node(self, node):
        """更新节点的高度和平衡因子"""
        if node:
            node.height = 1 + max(self.get_height(node.left), 
                                 self.get_height(node.right))
            node.balance_factor = self.get_balance_factor(node)
    
    def rotate_right(self, y):
        """右旋"""
        x = y.left
        T2 = x.right
        
        # 执行旋转
        x.right = y
        y.left = T2
        
        # 更新高度
        self.update_node(y)
        self.update_node(x)
        
        return x
    
    def rotate_left(self, x):
        """左旋"""
        y = x.right
        T2 = y.left
        
        # 执行旋转
        y.left = x
        x.right = T2
        
        # 更新高度
        self.update_node(x)
        self.update_node(y)
        
        return y
    
    def balance_node(self, node):
        """平衡节点"""
        self.update_node(node)
        
        # 获取平衡因子
        balance = node.balance_factor
        
        # 左左情况 - 右旋
        if balance > 1 and node.left.balance_factor >= 0:
            print(f"右旋平衡节点 {node.key}")
            return self.rotate_right(node)
        
        # 右右情况 - 左旋
        if balance < -1 and node.right.balance_factor <= 0:
            print(f"左旋平衡节点 {node.key}")
            return self.rotate_left(node)
        
        # 左右情况 - 先左旋后右旋
        if balance > 1 and node.left.balance_factor < 0:
            print(f"左右情况: 先左旋 {node.left.key}，后右旋 {node.key}")
            node.left = self.rotate_left(node.left)
            return self.rotate_right(node)
        
        # 右左情况 - 先右旋后左旋
        if balance < -1 and node.right.balance_factor > 0:
            print(f"右左情况: 先右旋 {node.right.key}，后左旋 {node.key}")
            node.right = self.rotate_right(node.right)
            return self.rotate_left(node)
        
        return node
    
    def insert(self, key):
        """插入节点"""
        print(f"插入节点: {key}")
        self.root = self._insert(self.root, key)
    
    def _insert(self, node, key):
        """递归插入辅助函数"""
        # 1. 执行标准BST插入
        if node is None:
            return AVLNode(key)
        
        if key < node.key:
            node.left = self._insert(node.left, key)
        elif key > node.key:
            node.right = self._insert(node.right, key)
        else:
            # 不允许重复值
            return node
        
        # 2. 更新高度和平衡因子
        self.update_node(node)
        
        # 3. 平衡树
        return self.balance_node(node)
    
    def delete(self, key):
        """删除节点"""
        print(f"删除节点: {key}")
        self.root = self._delete(self.root, key)
    
    def _delete(self, node, key):
        """递归删除辅助函数"""
        # 1. 标准BST删除
        if node is None:
            return node
        
        if key < node.key:
            node.left = self._delete(node.left, key)
        elif key > node.key:
            node.right = self._delete(node.right, key)
        else:
            # 找到要删除的节点
            if node.left is None:
                return node.right
            elif node.right is None:
                return node.left
            else:
                # 有两个子节点，找到右子树的最小值
                successor = self._find_min(node.right)
                node.key = successor.key
                node.right = self._delete(node.right, successor.key)
        
        if node is None:
            return node
        
        # 2. 更新高度和平衡因子
        self.update_node(node)
        
        # 3. 平衡树
        return self.balance_node(node)
    
    def _find_min(self, node):
        """找到最小值节点"""
        current = node
        while current.left is not None:
            current = current.left
        return current
    
    def search(self, key):
        """搜索节点"""
        return self._search(self.root, key)
    
    def _search(self, node, key):
        """递归搜索辅助函数"""
        if node is None or node.key == key:
            return node
        
        if key < node.key:
            return self._search(node.left, key)
        else:
            return self._search(node.right, key)
    
    def inorder_traversal(self):
        """中序遍历"""
        result = []
        self._inorder(self.root, result)
        return result
    
    def _inorder(self, node, result):
        """中序遍历辅助函数"""
        if node:
            self._inorder(node.left, result)
            result.append(node.key)
            self._inorder(node.right, result)
    
    def preorder_traversal(self):
        """前序遍历"""
        result = []
        self._preorder(self.root, result)
        return result
    
    def _preorder(self, node, result):
        """前序遍历辅助函数"""
        if node:
            result.append(node.key)
            self._preorder(node.left, result)
            self._preorder(node.right, result)
    
    def print_tree(self):
        """打印树结构"""
        print("树结构:")
        self._print_tree(self.root, "", True)
    
    def _print_tree(self, node, prefix, is_left):
        """打印树辅助函数"""
        if node:
            print(f"{prefix}{\'└── \' if is_left else \'├── \'}{node.key}")
            
            child_prefix = prefix + ("    " if is_left else "│   ")
            self._print_tree(node.right, child_prefix, False)
            self._print_tree(node.left, child_prefix, True)


# 测试代码
if __name__ == "__main__":
    avl = AVLTree()
    
    # 插入测试
    test_values = [10, 20, 30, 40, 50, 25]
    print("=== 插入测试 ===")
    for value in test_values:
        avl.insert(value)
    
    print("\\n=== 树结构 ===")
    avl.print_tree()
    
    print("\\n=== 遍历测试 ===")
    print(f"中序遍历: {avl.inorder_traversal()}")
    print(f"前序遍历: {avl.preorder_traversal()}")
    
    print("\\n=== 搜索测试 ===")
    search_key = 25
    result = avl.search(search_key)
    print(f"搜索 {search_key}: {\'找到\' if result else \'未找到\'}")
    
    print("\\n=== 删除测试 ===")
    avl.delete(25)
    
    print("\\n=== 删除后的树结构 ===")
    avl.print_tree()
    
    print(f"中序遍历: {avl.inorder_traversal()}")
'''
    with open('avl_tree.py', 'w') as f:
        f.write(content)
    return "AVL树代码已成功写入文件"