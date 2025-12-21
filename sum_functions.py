def sum_two_numbers(a, b):
    """
    Tính tổng hai số
    
    Args:
        a: Số thứ nhất
        b: Số thứ hai
        
    Returns:
        Tổng của a và b
    """
    return a + b

def sum_two_lists(list1, list2):
    """
    Tính tổng từng phần tử của hai list
    
    Args:
        list1: List số thứ nhất
        list2: List số thứ hai
        
    Returns:
        List chứa tổng từng cặp phần tử
    """
    if len(list1) != len(list2):
        raise ValueError("Hai list phải có cùng độ dài")
    
    return [a + b for a, b in zip(list1, list2)]

# Ví dụ sử dụng
if __name__ == "__main__":
    # Tính tổng hai số
    result1 = sum_two_numbers(5, 3)
    print(f"Tổng 5 + 3 = {result1}")
    
    # Tính tổng hai list
    list_a = [1, 2, 3]
    list_b = [4, 5, 6]
    result2 = sum_two_lists(list_a, list_b)
    print(f"Tổng hai list: {result2}")