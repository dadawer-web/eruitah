"""
平衡二叉树（AVL树）实现
AVL树是一种自平衡的二叉搜索树，任何节点的两个子树的高度差不超过1
"""

class Node:
    """树节点类"""
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None
        self.height = 1  # 节点高度，初始化为1

class AVLTree:
    """AVL平衡二叉树类"""
    
    def __init__(self):
        self.root = None
    
    def get_height(self, node):
        """获取节点高度"""
        if node is None:
            return 0
        return node.height
    
    def get_balance(self, node):
        """获取节点平衡因子（左子树高度 - 右子树高度）"""
        if node is None:
            return 0
        return self.get_height(node.left) - self.get_height(node.right)
    
    def update_height(self, node):
        """更新节点高度"""
        if node:
            node.height = 1 + max(
                self.get_height(node.left),
                self.get_height(node.right)
            )
    
    def right_rotate(self, y):
        """右旋操作"""
        x = y.left
        T2 = x.right
        
        # 执行旋转
        x.right = y
        y.left = T2
        
        # 更新高度
        self.update_height(y)
        self.update_height(x)
        
        return x
    
    def left_rotate(self, x):
        """左旋操作"""
        y = x.right
        T2 = y.left
        
        # 执行旋转
        y.left = x
        x.right = T2
        
        # 更新高度
        self.update_height(x)
        self.update_height(y)
        
        return y
    
    def insert(self, key):
        """插入节点"""
        self.root = self._insert(self.root, key)
    
    def _insert(self, node, key):
        """递归插入辅助函数"""
        # 1. 标准BST插入
        if node is None:
            return Node(key)
        
        if key < node.key:
            node.left = self._insert(node.left, key)
        elif key > node.key:
            node.right = self._insert(node.right, key)
        else:
            return node  # 不允许重复值
        
        # 2. 更新当前节点高度
        self.update_height(node)
        
        # 3. 获取平衡因子并检查是否失衡
        balance = self.get_balance(node)
        
        # 4. 执行平衡操作（4种情况）
        
        # 情况1：左左型 - 右旋
        if balance > 1 and key < node.left.key:
            return self.right_rotate(node)
        
        # 情况2：右右型 - 左旋
        if balance < -1 and key > node.right.key:
            return self.left_rotate(node)
        
        # 情况3：左右型 - 先左旋后右旋
        if balance > 1 and key > node.left.key:
            node.left = self.left_rotate(node.left)
            return self.right_rotate(node)
        
        # 情况4：右左型 - 先右旋后左旋
        if balance < -1 and key < node.right.key:
            node.right = self.right_rotate(node.right)
            return self.left_rotate(node)
        
        return node
    
    def delete(self, key):
        """删除节点"""
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
            # 节点有一个或零个子节点
            if node.left is None:
                return node.right
            elif node.right is None:
                return node.left
            else:
                # 有两个子节点：找到右子树的最小值
                temp = self._min_value_node(node.right)
                node.key = temp.key
                node.right = self._delete(node.right, temp.key)
        
        # 如果树只有一个节点，直接返回
        if node is None:
            return node
        
        # 2. 更新高度
        self.update_height(node)
        
        # 3. 获取平衡因子并重新平衡
        balance = self.get_balance(node)
        
        # 4. 执行平衡操作（4种情况）
        
        # 情况1：左左型
        if balance > 1 and self.get_balance(node.left) >= 0:
            return self.right_rotate(node)
        
        # 情况2：左右型
        if balance > 1 and self.get_balance(node.left) < 0:
            node.left = self.left_rotate(node.left)
            return self.right_rotate(node)
        
        # 情况3：右右型
        if balance < -1 and self.get_balance(node.right) <= 0:
            return self.left_rotate(node)
        
        # 情况4：右左型
        if balance < -1 and self.get_balance(node.right) > 0:
            node.right = self.right_rotate(node.right)
            return self.left_rotate(node)
        
        return node
    
    def _min_value_node(self, node):
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
        if node is None:
            return False
        if key == node.key:
            return True
        elif key < node.key:
            return self._search(node.left, key)
        else:
            return self._search(node.right, key)
    
    def inorder_traversal(self):
        """中序遍历（升序排列）"""
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
        """以树形结构打印树"""
        self._print_tree(self.root, 0)
    
    def _print_tree(self, node, level):
        """树形打印辅助函数"""
        if node:
            self._print_tree(node.right, level + 1)
            print("    " * level + str(node.key))
            self._print_tree(node.left, level + 1)


# 测试代码
if __name__ == "__main__":
    # 创建AVL树
    avl = AVLTree()
    
    # 插入节点
    keys = [10, 20, 30, 40, 50, 25]
    print("插入节点:", keys)
    
    for key in keys:
        avl.insert(key)
    
    print("\n中序遍历（有序）:")
    print(avl.inorder_traversal())
    
    print("\n前序遍历:")
    print(avl.preorder_traversal())
    
    print("\n树形结构:")
    avl.print_tree()
    
    # 搜索测试
    print("\n搜索测试:")
    print("搜索 30:", avl.search(30))
    print("搜索 100:", avl.search(100))
    
    # 删除测试
    print("\n删除节点 30:")
    avl.delete(30)
    print("中序遍历:", avl.inorder_traversal())
    print("树形结构:")
    avl.print_tree()