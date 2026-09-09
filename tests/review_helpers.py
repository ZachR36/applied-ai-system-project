"""Explicit confirmations for existing scoring fixtures, not application behavior."""


def confirmed_request(engine, request, **kwargs):
    draft = engine.prepare_request(request, kwargs.get('base_profile'))
    # These existing fixtures intentionally exercise the user opting into
    # profile-based suggestions after acknowledging an unspecified request.
    if request == 'surprise me':
        draft.omit_unrecognized()
    confirmed = draft.confirm()
    return engine.process_user_request(request, confirmed_preferences=confirmed, **kwargs)
