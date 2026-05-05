class AVLNode:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None
        self.height = 1


class AVLTree:
    def __init__(self):
        self.root = None

    def get_height(self, node):
        if not node:
            return 0
        return node.height

    def get_balance(self, node):
        if not node:
            return 0
        return self.get_height(node.left) - self.get_height(node.right)

    def update_height(self, node):
        if node:
            node.height = 1 + max(self.get_height(node.left), self.get_height(node.right))

    def rotate_right(self, y):
        """右旋转"""
        x = y.left
        T2 = x.right

        # 执行旋转
        x.right = y
        y.left = T2

        # 更新高度
        self.update_height(y)
        self.update_height(x)

        return x

    def rotate_left(self, x):
        """左旋转"""
        y = x.right
        T2 = y.left

        # 执行旋转
        y.left = x
        x.right = T2

        # 更新高度
        self.update_height(x)
        self.update_height(y)

        return y

    def insert(self, root, key):
        """插入节点并保持平衡"""
        # 1. 正常的BST插入
        if not root:
            return AVLNode(key)
        
        if key < root.key:
            root.left = self.insert(root.left, key)
        elif key > root.key:
            root.right = self.insert(root.right, key)
        else:
            return root  # 不允许重复键

        # 2. 更新节点高度
        self.update_height(root)

        # 3. 获取平衡因子
        balance = self.get_balance(root)

        # 4. 如果节点不平衡，则有4种情况
        # 左左情况
        if balance > 1 and key < root.left.key:
            return self.rotate_right(root)

        # 右右情况
        if balance < -1 and key > root.right.key:
            return self.rotate_left(root)

        # 左右情况
        if balance > 1 and key > root.left.key:
            root.left = self.rotate_left(root.left)
            return self.rotate_right(root)

        # 右左情况
        if balance < -1 and key < root.right.key:
            root.right = self.rotate_right(root.right)
            return self.rotate_left(root)

        return root

    def insert_key(self, key):
        """插入键的公共方法"""
        self.root = self.insert(self.root, key)

    def delete(self, root, key):
        """删除节点并保持平衡"""
        # 1. 正常的BST删除
        if not root:
            return root

        if key < root.key:
            root.left = self.delete(root.left, key)
        elif key > root.key:
            root.right = self.delete(root.right, key)
        else:
            # 节点有一个或没有子节点
            if root.left is None:
                return root.right
            elif root.right is None:
                return root.left
            
            # 节点有两个子节点：获取中序后继（右子树的最小值）
            temp = self.get_min_value_node(root.right)
            root.key = temp.key
            root.right = self.delete(root.right, temp.key)

        # 如果树只有一个节点，返回
        if root is None:
            return root

        # 2. 更新节点高度
        self.update_height(root)

        # 3. 获取平衡因子
        balance = self.get_balance(root)

        # 4. 如果节点不平衡，则有4种情况
        # 左左情况
        if balance > 1 and self.get_balance(root.left) >= 0:
            return self.rotate_right(root)

        # 左右情况
        if balance > 1 and self.get_balance(root.left) < 0:
            root.left = self.rotate_left(root.left)
            return self.rotate_right(root)

        # 右右情况
        if balance < -1 and self.get_balance(root.right) <= 0:
            return self.rotate_left(root)

        # 右左情况
        if balance < -1 and self.get_balance(root.right) > 0:
            root.right = self.rotate_right(root.right)
            return self.rotate_left(root)

        return root

    def delete_key(self, key):
        """删除键的公共方法"""
        self.root = self.delete(self.root, key)

    def get_min_value_node(self, root):
        """获取最小值节点"""
        if root is None or root.left is None:
            return root
        return self.get_min_value_node(root.left)

    def search(self, root, key):
        """搜索节点"""
        if root is None or root.key == key:
            return root
        
        if root.key < key:
            return self.search(root.right, key)
        
        return self.search(root.left, key)

    def search_key(self, key):
        """搜索键的公共方法"""
        return self.search(self.root, key)

    def inorder_traversal(self, root):
        """中序遍历"""
        result = []
        if root:
            result.extend(self.inorder_traversal(root.left))
            result.append(root.key)
            result.extend(self.inorder_traversal(root.right))
        return result

    def preorder_traversal(self, root):
        """前序遍历"""
        result = []
        if root:
            result.append(root.key)
            result.extend(self.preorder_traversal(root.left))
            result.extend(self.preorder_traversal(root.right))
        return result

    def postorder_traversal(self, root):
        """后序遍历"""
        result = []
        if root:
            result.extend(self.postorder_traversal(root.left))
            result.extend(self.postorder_traversal(root.right))
            result.append(root.key)
        return result

    def get_inorder(self):
        """获取中序遍历结果"""
        return self.inorder_traversal(self.root)

    def get_preorder(self):
        """获取前序遍历结果"""
        return self.preorder_traversal(self.root)

    def get_postorder(self):
        """获取后序遍历结果"""
        return self.postorder_traversal(self.root)

    def print_tree(self, root, level=0, prefix="Root: "):
        """打印树结构"""
        if root is not None:
            print(" " * (level * 4) + prefix + str(root.key) + f" (h:{root.height})")
            if root.left is not None or root.right is not None:
                if root.left:
                    self.print_tree(root.left, level + 1, "L--- ")
                else:
                    print(" " * ((level + 1) * 4) + "L--- None")
                if root.right:
                    self.print_tree(root.right, level + 1, "R--- ")
                else:
                    print(" " * ((level + 1) * 4) + "R--- None")

    def display(self):
        """显示树结构"""
        self.print_tree(self.root)