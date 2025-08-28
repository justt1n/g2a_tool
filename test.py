import logging

from logic.auth import AuthHandler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    auth_handler = AuthHandler()

    try:
        print("First call:")
        headers1 = auth_handler.get_auth_headers()
        print(headers1)

        print("\nSecond call (should use cached token):")
        headers2 = auth_handler.get_auth_headers()
        print(headers2)

        print("\nForcing token expiration to test renewal...")
        auth_handler._token_expires_at = 0.0
        headers3 = auth_handler.get_auth_headers()
        print(headers3)

    except ConnectionError as e:
        print(f"Error: {e}")
    finally:
        auth_handler.close()

