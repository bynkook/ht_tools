from .models import BoardModerator


def is_board_admin(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


def is_board_moderator(user, board):
    if not user or not user.is_authenticated:
        return False
    if is_board_admin(user):
        return True
    return BoardModerator.objects.filter(board=board, user=user).exists()


def get_board_permission_flags(user, board):
    admin = is_board_admin(user)
    moderator = is_board_moderator(user, board)
    return {
        'is_admin': admin,
        'is_board_moderator': moderator,
        'can_create': bool(board.is_active and (admin or (moderator and board.allow_create))),
        'can_update': bool(board.is_active and (admin or (moderator and board.allow_update))),
        'can_delete': bool(board.is_active and (admin or (moderator and board.allow_delete))),
    }
