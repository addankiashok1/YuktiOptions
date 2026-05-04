class DuplicateEmailError(Exception):
    pass


class DuplicateMobileError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class WalletNotFoundError(Exception):
    pass


class InsufficientBalanceError(Exception):
    pass
