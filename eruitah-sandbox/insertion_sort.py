"""
插入排序算法实现 (Insertion Sort)

算法思路：
    插入排序的工作原理类似于整理扑克牌。
    1. 从第二个元素开始（第一个元素默认已排序）
    2. 将当前元素（称为"key"）取出，与前面已排序部分的元素从右到左逐个比较
    3. 如果前面的元素大于当前元素，就将前面的元素向后移动一位
    4. 找到合适的位置后，将当前元素插入
    5. 重复这个过程，直到所有元素都已排序

算法特性：
    - 稳定排序：相等元素的相对顺序不会改变
    - 原地排序：不需要额外的数组空间
    - 适合小规模数据或近乎有序的数据
"""


def insertion_sort(arr: list) -> list:
    """
    插入排序算法实现
    
    Args:
        arr: 待排序的列表
        
    Returns:
        排序后的新列表（不修改原数组）
    """
    # 创建原数组的副本，避免修改原数组
    result = arr.copy()
    n = len(result)
    
    # 从第二个元素开始遍历（索引1），因为第一个元素默认已排序
    for i in range(1, n):
        # 当前需要插入的元素（key）
        key = result[i]
        
        # j 指向已排序部分的最后一个元素
        j = i - 1
        
        # 将 key 与已排序部分从右到左逐个比较
        # 如果已排序元素大于 key，则将其向后移动一位
        while j >= 0 and result[j] > key:
            result[j + 1] = result[j]  # 元素向后移动
            j -= 1  # 继续向前比较
        
        # 找到合适的位置，插入 key
        # j+1 就是 key 应该在的位置
        result[j + 1] = key
    
    return result


def insertion_sort_inplace(arr: list) -> None:
    """
    原地插入排序（直接修改原数组）
    
    Args:
        arr: 待排序的列表（会被直接修改）
    """
    n = len(arr)
    
    for i in range(1, n):
        key = arr[i]
        j = i - 1
        
        while j >= 0 and arr[j] > key:
            arr[j + 1] = arr[j]
            j -= 1
        
        arr[j + 1] = key


def print_array(arr: list, name: str = "数组") -> None:
    """辅助函数：打印数组"""
    print(f"{name}: {arr}")


if __name__ == "__main__":
    print("=" * 50)
    print("插入排序算法演示")
    print("=" * 50)
    
    # 测试用例1：普通数组
    print("\n【测试1】普通数组排序")
    test1 = [64, 34, 25, 12, 22, 11, 90]
    print_array(test1, "排序前")
    result1 = insertion_sort(test1)
    print_array(result1, "排序后")
    print_array(test1, "原数组")  # 原数组不变
    
    # 测试用例2：已排序数组（最好情况）
    print("\n【测试2】已排序数组（最好情况 O(n)）")
    test2 = [1, 2, 3, 4, 5, 6, 7]
    print_array(test2, "排序前")
    result2 = insertion_sort(test2)
    print_array(result2, "排序后")
    
    # 测试用例3：逆序数组（最坏情况）
    print("\n【测试3】逆序数组（最坏情况 O(n²)）")
    test3 = [7, 6, 5, 4, 3, 2, 1]
    print_array(test3, "排序前")
    result3 = insertion_sort(test3)
    print_array(result3, "排序后")
    
    # 测试用例4：包含重复元素
    print("\n【测试4】包含重复元素")
    test4 = [5, 2, 8, 2, 9, 1, 5, 5]
    print_array(test4, "排序前")
    result4 = insertion_sort(test4)
    print_array(result4, "排序后")
    
    # 测试用例5：原地排序
    print("\n【测试5】原地排序")
    test5 = [38, 27, 43, 3, 9, 82, 10]
    print_array(test5, "排序前")
    insertion_sort_inplace(test5)
    print_array(test5, "排序后（原数组已被修改）")
    
    # 测试用例6：边界情况
    print("\n【测试6】边界情况")
    test6a = [42]  # 单元素
    test6b = []     # 空数组
    print_array(insertion_sort(test6a), "单元素排序")
    print_array(insertion_sort(test6b), "空数组排序")
    
    # 测试用例7：负数和小数
    print("\n【测试7】负数和小数")
    test7 = [3.14, -2, 0, 1.5, -3.7, 2, 0.5]
    print_array(test7, "排序前")
    result7 = insertion_sort(test7)
    print_array(result7, "排序后")
    
    print("\n" + "=" * 50)
    print("算法复杂度分析")
    print("=" * 50)
    print("""
时间复杂度：
    • 最好情况：O(n)
      当数组已经有序时，内层循环不需要执行任何移动操作
      只需要遍历一次数组即可
    
    • 最坏情况：O(n²)
      当数组是逆序时，每次插入都需要移动所有已排序的元素
    
    • 平均情况：O(n²)
      平均每次插入需要移动约一半的已排序元素

空间复杂度：
    • O(1)
    • 插入排序是原地排序算法，只需要常数级别的额外空间
    • 只使用了几个临时变量（key, j 等）

稳定性：
    • 稳定排序
    • 相等元素的相对顺序在排序后保持不变
    • 因为只有当元素严格大于 key 时才移动

适用场景：
    1. 小规模数据（n < 50）
    2. 数据近乎有序（此时接近 O(n)）
    3. 在线算法（可以边接收数据边排序）
    4. 作为其他排序算法（如快速排序）的子程序
""")
