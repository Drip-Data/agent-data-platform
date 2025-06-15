def gcd(a: int, b: int) -> int:
    """
    使用欧几里得算法计算两个整数的最大公约数 (GCD)。

    参数:
    a (int): 第一个整数。
    b (int): 第二个整数。

    返回:
    int: 两个整数的最大公约数。
    """
    while b:
        a, b = b, a % b
    return a

if __name__ == "__main__":
    # 示例用法
    print(f"GCD of 48 and 18 is: {gcd(48, 18)}") # 预期输出: 6
    print(f"GCD of 101 and 103 is: {gcd(101, 103)}") # 预期输出: 1
    print(f"GCD of 0 and 5 is: {gcd(0, 5)}") # 预期输出: 5
    print(f"GCD of 7 and 0 is: {gcd(7, 0)}") # 预期输出: 7