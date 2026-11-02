import 'dart:io';
import 'dart:math' as math;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/models/my_systems.dart';

/// Pure spatial-layout helpers for the systems grid.
///
/// These functions were extracted verbatim from `_MySystemsGridState` so the
/// packing/geometry math can be unit-tested in isolation and reused without a
/// live widget. They hold no state — the grid's memoization cache stays in the
/// widget, which calls [buildVirtualGrid] and stores the result.

/// Packs [cards] into a virtual spatial grid of [cols] columns.
///
/// Returns a row-major matrix where each cell holds the index of the card
/// occupying it, or `-1` for an empty slot. 'Recent Games' cards (`isGame`)
/// expand to a 3x2 block on wide displays (`cols >= 3`); every other card
/// occupies a single cell. Cards are placed by a first-fit scan for the first
/// spatial slot large enough to hold their span.
///
/// [uniformSpans] (RewindBox Glacier) keeps every card, the recent game
/// included, on a single cell: one card template for the whole grid.
List<List<int>> buildVirtualGrid(
  List<SystemInfo> cards,
  int cols, {
  bool uniformSpans = false,
}) {
  final List<List<int>> grid = [];

  // 'Recent Games' cards expand to 3x2 on high-resolution displays — but
  // not on iOS, where that hero treatment dwarfs every other card on a
  // phone-sized screen (see the matching render-time fix in
  // my_systems_grid.dart). Both places need to agree, or this function
  // reserves 3x2 cells while the card only ever draws at 1x1, leaving a
  // visible gap where the reserved-but-unused columns sit.
  int getSpanW(SystemInfo card) =>
      (!uniformSpans && card.isGame && cols >= 3 && !Platform.isIOS) ? 3 : 1;
  int getSpanH(SystemInfo card) =>
      (!uniformSpans && card.isGame && cols >= 3 && !Platform.isIOS) ? 2 : 1;

  for (int i = 0; i < cards.length; i++) {
    final card = cards[i];
    final w = getSpanW(card);
    final h = getSpanH(card);

    // Recursive scan for the first available spatial slot that fits the component spans.
    int foundRow = 0;
    int foundCol = 0;
    bool fits = false;

    while (!fits) {
      while (grid.length <= foundRow + h - 1) {
        grid.add(List<int>.filled(cols, -1));
      }

      if (foundCol + w <= cols) {
        bool overlap = false;
        for (int r = foundRow; r < foundRow + h; r++) {
          for (int c = foundCol; c < foundCol + w; c++) {
            if (grid[r][c] != -1) {
              overlap = true;
              break;
            }
          }
          if (overlap) break;
        }

        if (!overlap) {
          fits = true;
        } else {
          foundCol++;
          if (foundCol >= cols) {
            foundCol = 0;
            foundRow++;
          }
        }
      } else {
        foundCol = 0;
        foundRow++;
      }
    }

    // Commit the spatial allocation to the grid matrix.
    for (int r = foundRow; r < foundRow + h; r++) {
      for (int c = foundCol; c < foundCol + w; c++) {
        grid[r][c] = i;
      }
    }
  }

  return grid;
}

/// Spatial search for the nearest neighbor in a row with potential layout gaps.
///
/// Expands outward from [col] within [row] of [grid], returning the first
/// occupied card index found, or `-1` if the row has no other occupant.
int findNearestInRow(List<List<int>> grid, int row, int col) {
  final rowItems = grid[row];
  final cols = rowItems.length;

  for (int dist = 1; dist < cols; dist++) {
    if (col - dist >= 0 && rowItems[col - dist] != -1) {
      return rowItems[col - dist];
    }
    if (col + dist < cols && rowItems[col + dist] != -1) {
      return rowItems[col + dist];
    }
  }
  return -1;
}

/// Dynamically computes grid layout dimensions based on viewport constraints.
///
/// [screenWidth] is the width available to the grid (already net of any outer
/// inset), [cols] the column count, and [childAspectRatio] the card aspect
/// ratio (a non-1 ratio denotes a system card, which gets extra height for its
/// logo footer). Returns the item/row sizing and spacing map consumed by the
/// grid delegate.
Map<String, double> calculateGridDimensions({
  required double screenWidth,
  required int cols,
  required double childAspectRatio,
}) {
  final crossAxisSpacing = 6.0.r;
  final mainAxisSpacing = 6.0.r;

  final totalSpacing = crossAxisSpacing * (cols - 1);
  final availableWidth = screenWidth - totalSpacing;
  final itemWidth = availableWidth / cols;

  // For game cards (childAspectRatio = 1) use traditional square calculation.
  // For system cards (childAspectRatio != 1) add extra height for logo footer.
  final double itemHeight;
  if (childAspectRatio != 1) {
    itemHeight = itemWidth + 32.r;
  } else {
    itemHeight = itemWidth / childAspectRatio;
  }
  final rowHeight = itemHeight + mainAxisSpacing;

  return {
    'itemWidth': itemWidth,
    'itemHeight': itemHeight,
    'rowHeight': rowHeight,
    'crossAxisSpacing': crossAxisSpacing,
    'mainAxisSpacing': mainAxisSpacing,
  };
}

/// RewindBox Glacier grid geometry.
///
/// Every card has the same size. The width follows the columns (the user's
/// card size preference) and the reference 16 px gutter of a 1675 px grid;
/// the height makes whole rows fill [viewportHeight]: two at the reference
/// (the approved composition: two full rows at 1837 x 856), more on a taller
/// screen such as an iPad when the library has them ([rows]), always kept
/// between 0.78 and 1.12 of the width so cards stay cards; a compact screen
/// scrolls sooner.
Map<String, double> calculateGlacierGridDimensions({
  required double width,
  required double viewportHeight,
  required int cols,
  int? rows,
}) {
  final gap = math.max(6.0, width * (16 / 1675));
  final itemWidth = (width - gap * (cols - 1)) / cols;
  const reference = 246 / 264;
  final natural = ((viewportHeight + gap) / (itemWidth * reference + gap))
      .round();
  final visibleRows = math.max(2, math.min(natural, rows ?? natural));
  final fit = (viewportHeight - gap * (visibleRows - 1)) / visibleRows;
  final itemHeight = fit.isFinite && fit > 0
      ? fit.clamp(itemWidth * .78, itemWidth * 1.12).toDouble()
      : itemWidth * reference;
  return {
    'itemWidth': itemWidth,
    'itemHeight': itemHeight,
    'rowHeight': itemHeight + gap,
    'crossAxisSpacing': gap,
    'mainAxisSpacing': gap,
  };
}
