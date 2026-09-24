def read_int(prompt: str, minimum: int, maximum: int, default: int) -> int:
    while True:
        try:
            value = int(input(prompt).strip() or default)
            if minimum <= value <= maximum:
                return value
        except ValueError:
            pass
        print(f'請輸入 {minimum} 到 {maximum} 之間的整數。')


def mask_private(value: str) -> str:
    return '*' * max(0, len(value) - 3) + value[-3:]
