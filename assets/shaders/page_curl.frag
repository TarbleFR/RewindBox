#version 460 core
#include <flutter/runtime_effect.glsl>

// Page curl of the Library readers (docs/library-books-3d-plan.md § 3.4).
//
// The turning page lies in uPage. It rolls around a cylinder of radius
// uRadius whose axis passes through uCorner, perpendicular to uDirection
// (unit vector pointing toward the edge that lifts). Points of the page
// beyond the axis wrap around the cylinder (front side on the lower half,
// back side on the upper half) and, past half a turn, lie flat on top of
// the page, folded back toward the hinge. Everything is in the logical
// pixels of the canvas (FlutterFragCoord), like the geometry computed by
// LibraryPageCurlGeometry in lib/screens/library_screen/reader/
// library_page_curl.dart, which also drives the painter fallback.
//
// Images are drawn BoxFit.contain in the page over the paper colour: centred
// (single pages) or aligned toward the hinge (pages of a two-page spread).
// The back side shows uBack mirrored (the page that lands on the other half
// of a spread) or, without it, the paper with the front faintly showing
// through. An image size of 0 means "no image".

uniform vec2 uSize;        // canvas size
uniform vec4 uPage;        // turning page: left, top, width, height
uniform vec2 uCorner;      // a point of the curl axis
uniform vec2 uDirection;   // unit normal of the axis, toward the lifting edge
uniform float uRadius;     // curl radius
uniform float uRtl;        // 1: the hinge is the right edge of the page
uniform float uAlign;      // 1: images aligned toward the hinge, 0: centred
uniform float uShadow;     // shadow strength (0 at rest and when landed)
uniform vec2 uFrontSize;   // image sizes in pixels, 0 when absent
uniform vec2 uBackSize;
uniform vec2 uUnderSize;
uniform vec4 uPaper;       // paper colour, premultiplied

uniform sampler2D uFront;
uniform sampler2D uBack;
uniform sampler2D uUnder;

out vec4 fragColor;

const float PI = 3.14159265359;

vec4 over(vec4 dst, vec4 src) {
    return src + dst * (1.0 - src.a);
}

// Coverage of point q by the page, antialiased over one pixel.
float pageCoverage(vec2 q) {
    vec2 lo = q - uPage.xy;
    vec2 hi = uPage.xy + uPage.zw - q;
    float d = min(min(lo.x, hi.x), min(lo.y, hi.y));
    return clamp(d + 0.5, 0.0, 1.0);
}

// Distance from q to the page (0 inside).
float outsideDistance(vec2 q) {
    vec2 lo = uPage.xy - q;
    vec2 hi = q - (uPage.xy + uPage.zw);
    return length(max(max(lo, hi), vec2(0.0)));
}

// Texture coordinate (xy) of page point q for an image drawn BoxFit.contain
// in the page, and the antialiased coverage of the image (z). mirrored: the
// back side (the page seen from behind).
vec3 imageCoord(vec2 q, vec2 imageSize, float mirrored) {
    if (imageSize.x <= 0.0 || imageSize.y <= 0.0) {
        return vec3(0.0);
    }
    vec2 uv = (q - uPage.xy) / uPage.zw;
    float alignX = uAlign > 0.5 ? (uRtl > 0.5 ? 1.0 : 0.0) : 0.5;
    if (mirrored > 0.5) {
        uv.x = 1.0 - uv.x;
        alignX = 1.0 - alignX;
    }
    float pageAspect = uPage.z / max(uPage.w, 0.0001);
    float imageAspect = imageSize.x / max(imageSize.y, 0.0001);
    vec2 scale = imageAspect > pageAspect
        ? vec2(1.0, pageAspect / imageAspect)
        : vec2(imageAspect / pageAspect, 1.0);
    vec2 offset = vec2((1.0 - scale.x) * alignX, (1.0 - scale.y) * 0.5);
    vec2 st = (uv - offset) / scale;
    vec2 extent = scale * uPage.zw;
    float inside = min(min(st.x, 1.0 - st.x) * extent.x, min(st.y, 1.0 - st.y) * extent.y);
    return vec3(clamp(st, 0.0, 1.0), clamp(inside + 0.5, 0.0, 1.0));
}

vec4 onPaper(vec4 image, float coverage) {
    return mix(uPaper, over(uPaper, image), coverage);
}

vec4 frontColor(vec2 q) {
    vec3 c = imageCoord(q, uFrontSize, 0.0);
    return onPaper(texture(uFront, c.xy), c.z);
}

vec4 backColor(vec2 q) {
    if (uBackSize.x > 0.0) {
        vec3 c = imageCoord(q, uBackSize, 1.0);
        return onPaper(texture(uBack, c.xy), c.z);
    }
    // Paper seen from behind: the front shows through, mirrored by the fold.
    return mix(uPaper, frontColor(q), 0.12);
}

vec4 underColor(vec2 q) {
    if (uUnderSize.x > 0.0) {
        vec3 c = imageCoord(q, uUnderSize, 0.0);
        return onPaper(texture(uUnder, c.xy), c.z);
    }
    return uPaper;
}

void main() {
    vec2 p = FlutterFragCoord().xy;
    vec2 n = uDirection;
    float r = max(uRadius, 0.0001);
    float d = dot(p - uCorner, n);
    vec2 foot = p - n * d;
    float shadowWidth = max(min(uSize.x, uSize.y) * 0.04, 4.0) + r;
    vec4 color = vec4(0.0);

    // Page revealed under the curl, darkened by the roll's shadow.
    float inPage = pageCoverage(p);
    if (inPage > 0.0) {
        vec4 under = underColor(p);
        float shade = uShadow * 0.45 * (1.0 - smoothstep(0.0, shadowWidth, d - r));
        under.rgb *= 1.0 - shade;
        color = under * inPage;
    }

    // Flat part of the page that has not lifted yet.
    if (d <= 0.0 && inPage > 0.0) {
        color = over(color, frontColor(p) * inPage);
    }

    if (d >= 0.0 && d < r) {
        // Lower half of the roll: the front side, foreshortened and darker
        // toward the silhouette.
        float k = clamp(d / r, 0.0, 1.0);
        vec2 q = foot + n * (r * asin(k));
        float coverage = pageCoverage(q);
        if (coverage > 0.0) {
            vec4 front = frontColor(q);
            front.rgb *= 1.0 - 0.35 * k * k * k;
            color = over(color, front * coverage);
        }
    }

    // Drop shadow of the folded part on what lies beneath it.
    if (d < 0.0) {
        float e = outsideDistance(foot + n * (PI * r - d));
        if (e > 0.0) {
            float fall = 1.0 - smoothstep(0.0, shadowWidth, e);
            color = over(color, vec4(0.0, 0.0, 0.0, uShadow * 0.3 * fall * fall));
        }
    }

    if (d >= 0.0 && d < r) {
        // Upper half of the roll: the back side, lit at the top of the roll.
        float k = clamp(d / r, 0.0, 1.0);
        vec2 q = foot + n * (r * (PI - asin(k)));
        float coverage = pageCoverage(q);
        if (coverage > 0.0) {
            vec4 back = backColor(q);
            back.rgb *= 0.78 + 0.17 * (1.0 - k);
            color = over(color, back * coverage);
        }
    }

    if (d < 0.0) {
        // Folded part lying flat on top of the page: the back side.
        vec2 q = foot + n * (PI * r - d);
        float coverage = pageCoverage(q);
        if (coverage > 0.0) {
            vec4 back = backColor(q);
            back.rgb *= 0.85 + 0.1 * exp(d / r);
            color = over(color, back * coverage);
        }
    }

    fragColor = color;
}
