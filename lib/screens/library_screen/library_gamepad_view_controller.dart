/// Routes the controller input that `AppScreen` forwards to `LibraryScreen`
/// (d-pad, A, B, X) to the Library section currently shown inside it.
///
/// A section widget attaches its state as the delegate while it is mounted.
/// Every method returns whether the section handled the input; `back`
/// returning false lets `LibraryScreen` return to the hub.
abstract interface class LibraryGamepadViewDelegate {
  bool navigate(int dx, int dy);
  bool activate();
  bool back();
  bool secondary();
}

class LibraryGamepadViewController {
  LibraryGamepadViewDelegate? _delegate;

  bool get isAttached => _delegate != null;

  void attach(LibraryGamepadViewDelegate delegate) => _delegate = delegate;

  void detach(LibraryGamepadViewDelegate delegate) {
    if (identical(_delegate, delegate)) _delegate = null;
  }

  bool navigate(int dx, int dy) => _delegate?.navigate(dx, dy) ?? false;

  bool activate() => _delegate?.activate() ?? false;

  bool back() => _delegate?.back() ?? false;

  bool secondary() => _delegate?.secondary() ?? false;
}
