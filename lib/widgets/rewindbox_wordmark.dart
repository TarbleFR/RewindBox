import 'package:flutter/material.dart';

/// Text-based identity of the independent fork, not upstream artwork.
class RewindBoxWordmark extends StatelessWidget {
  const RewindBoxWordmark({super.key, this.width, this.height,
    this.fit = BoxFit.contain});
  final double? width;
  final double? height;
  final BoxFit fit;
  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'RewindBox',
      image: true,
      excludeSemantics: true,
      child: SizedBox(
        width: width,
        height: height,
        child: FittedBox(
          fit: fit,
          child: Text('RewindBox', maxLines: 1,
            style: TextStyle(fontSize: 48, fontWeight: FontWeight.w800,
              color: Theme.of(context).colorScheme.onSurface)),
        ),
      ),
    );
  }
}
