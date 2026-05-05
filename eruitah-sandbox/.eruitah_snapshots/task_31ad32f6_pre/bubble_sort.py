def bubble_sort(arr):
    """
    冒泡排序实现
    :param arr: 待排序的数组
    :return: 排序后的数组
    """
    n = len(arr)
    # 创建数组副本以避免修改原数组
    sorted_arr = arr.copy()
    
    # 外层循环控制排序轮数
    for i in range(n):
        # 标记是否发生交换，用于优化
        swapped = False
        # 内层循环进行相邻元素比较和交换
        for j in range(0, n - i - 1):
            # 如果前一个元素大于后一个元素，则交换它们
            if sorted_arr[j] > sorted_arr[j + 1]:
                sorted_arr[j], sorted_arr[j + 1] = sorted_arr[j + 1], sorted_arr[j]
                swapped = True
        # 如果这一轮没有发生交换，说明数组已经有序，可以提前结束
        if not swapped:
            break
    
    return sorted_arr

# 测试代码
if __name__ == "__main__":
    # 测试用例
    test_arr = [64, 34, 25, 12, 22, 11, 90]
    print("原始数组:", test_arr)
    
    sorted_arr = bubble_sort(test_arr)
    print("排序后数组:", sorted_arr)