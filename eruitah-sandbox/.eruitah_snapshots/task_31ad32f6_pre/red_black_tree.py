# 红黑树实现

class Color:
    RED = 0
    BLACK = 1

class Node:
    def __init__(self, key, color=Color.RED, left=None, right=None, parent=None):
        self.key = key
        self.color = color
        self.left = left if left else Leaf()
        self.right = right if right else Leaf()
        self.parent = parent if parent else None

class Leaf:
    def __init__(self):
        self.color = Color.BLACK
        self.key = None
    
    def is_leaf(self):
        return True

class RedBlackTree:
    def __init__(self):
        self.NIL = Leaf()
        self.root = self.NIL
    
    def insert(self, key):
        """插入节点并保持红黑树性质"""
        new_node = Node(key)
        self._insert_node(new_node)
    
    def _insert_node(self, new_node):
        """内部插入方法"""
        y = None
        x = self.root
        
        # 找到插入位置
        while x != self.NIL:
            y = x
            if new_node.key < x.key:
                x = x.left
            else:
                x = x.right
        
        new_node.parent = y
        
        # 插入新节点
        if y is None:
            self.root = new_node
        elif new_node.key < y.key:
            y.left = new_node
        else:
            y.right = new_node
        
        # 新节点初始为红色
        new_node.left = self.NIL
        new_node.right = self.NIL
        new_node.color = Color.RED
        
        # 修复红黑树性质
        self._fix_insert(new_node)
    
    def _fix_insert(self, k):
        """修复插入后的红黑树性质"""
        while k != self.root and k.parent.color == Color.RED:
            if k.parent == k.parent.parent.left:
                u = k.parent.parent.right
                
                if u.color == Color.RED:
                    # 情况1: 叔叔节点是红色
                    u.color = Color.BLACK
                    k.parent.color = Color.BLACK
                    k.parent.parent.color = Color.RED
                    k = k.parent.parent
                else:
                    if k == k.parent.right:
                        # 情况2: k是右孩子
                        k = k.parent
                        self._left_rotate(k)
                    
                    # 情况3: k是左孩子
                    k.parent.color = Color.BLACK
                    k.parent.parent.color = Color.RED
                    self._right_rotate(k.parent.parent)
            else:
                u = k.parent.parent.left
                
                if u.color == Color.RED:
                    # 镜像情况1
                    u.color = Color.BLACK
                    k.parent.color = Color.BLACK
                    k.parent.parent.color = Color.RED
                    k = k.parent.parent
                else:
                    if k == k.parent.left:
                        # 镜像情况2
                        k = k.parent
                        self._right_rotate(k)
                    
                    # 镜像情况3
                    k.parent.color = Color.BLACK
                    k.parent.parent.color = Color.RED
                    self._left_rotate(k.parent.parent)
        
        self.root.color = Color.BLACK
    
    def _left_rotate(self, x):
        """左旋转"""
        y = x.right
        x.right = y.left
        
        if y.left != self.NIL:
            y.left.parent = x
        
        y.parent = x.parent
        
        if x.parent is None:
            self.root = y
        elif x == x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y
        
        y.left = x
        x.parent = y
    
    def _right_rotate(self, y):
        """右旋转"""
        x = y.left
        y.left = x.right
        
        if x.right != self.NIL:
            x.right.parent = y
        
        x.parent = y.parent
        
        if y.parent is None:
            self.root = x
        elif y == y.parent.right:
            y.parent.right = x
        else:
            y.parent.left = x
        
        x.right = y
        y.parent = x
    
    def search(self, key):
        """搜索节点"""
        current = self.root
        while current != self.NIL:
            if key == current.key:
                return current
            elif key < current.key:
                current = current.left
            else:
                current = current.right
        return None
    
    def delete(self, key):
        """删除节点"""
        node = self.search(key)
        if node is None:
            return
        
        self._delete_node(node)
    
    def _delete_node(self, z):
        """内部删除方法"""
        y = z
        y_original_color = y.color
        
        if z.left == self.NIL:
            x = z.right
            self._transplant(z, z.right)
        elif z.right == self.NIL:
            x = z.left
            self._transplant(z, z.left)
        else:
            y = self._minimum(z.right)
            y_original_color = y.color
            x = y.right
            
            if y.parent == z:
                x.parent = y
            else:
                self._transplant(y, y.right)
                y.right = z.right
                y.right.parent = y
            
            self._transplant(z, y)
            y.left = z.left
            y.left.parent = y
            y.color = z.color
        
        if y_original_color == Color.BLACK:
            self._fix_delete(x)
    
    def _transplant(self, u, v):
        """用v替换u"""
        if u.parent is None:
            self.root = v
        elif u == u.parent.left:
            u.parent.left = v
        else:
            u.parent.right = v
        
        v.parent = u.parent
    
    def _fix_delete(self, x):
        """修复删除后的红黑树性质"""
        while x != self.root and x.color == Color.BLACK:
            if x == x.parent.left:
                w = x.parent.right
                
                if w.color == Color.RED:
                    w.color = Color.BLACK
                    x.parent.color = Color.RED
                    self._left_rotate(x.parent)
                    w = x.parent.right
                
                if w.left.color == Color.BLACK and w.right.color == Color.BLACK:
                    w.color = Color.RED
                    x = x.parent
                else:
                    if w.right.color == Color.BLACK:
                        w.left.color = Color.BLACK
                        w.color = Color.RED
                        self._right_rotate(w)
                        w = x.parent.right
                    
                    w.color = x.parent.color
                    x.parent.color = Color.BLACK
                    w.right.color = Color.BLACK
                    self._left_rotate(x.parent)
                    x = self.root
            else:
                w = x.parent.left
                
                if w.color == Color.RED:
                    w.color = Color.BLACK
                    x.parent.color = Color.RED
                    self._right_rotate(x.parent)
                    w = x.parent.left
                
                if w.right.color == Color.BLACK and w.left.color == Color.BLACK:
                    w.color = Color.RED
                    x = x.parent
                else:
                    if w.left.color == Color.BLACK:
                        w.right.color = Color.BLACK
                        w.color = Color.RED
                        self._left_rotate(w)
                        w = x.parent.left
                    
                    w.color = x.parent.color
                    x.parent.color = Color.BLACK
                    w.left.color = Color.BLACK
                    self._right_rotate(x.parent)
                    x = self.root
        
        x.color = Color.BLACK
    
    def _minimum(self, node):
        """找到最小节点"""
        while node.left != self.NIL:
            node = node.left
        return node
    
    def inorder(self):
        """中序遍历"""
        result = []
        self._inorder_helper(self.root, result)
        return result
    
    def _inorder_helper(self, node, result):
        """中序遍历辅助方法"""
        if node != self.NIL:
            self._inorder_helper(node.left, result)
            result.append(node.key)
            self._inorder_helper(node.right, result)

# 测试代码
if __name__ == "__main__":
    tree = RedBlackTree()
    
    # 插入测试
    keys = [10, 20, 30, 15, 25, 5, 1, 50, 60, 22]
    print("插入节点:", keys)
    for key in keys:
        tree.insert(key)
    
    print("中序遍历:", tree.inorder())
    
    # 搜索测试
    print("搜索25:", tree.search(25) is not None)
    print("搜索100:", tree.search(100) is not None)
    
    # 删除测试
    print("删除20后:")
    tree.delete(20)
    print("中序遍历:", tree.inorder())
    
    print("删除10后:")
    tree.delete(10)
    print("中序遍历:", tree.inorder())