// Model of MoltenVK 1.4.2 MVKPresentableSwapchainImage drawable handling (MVKImage.mm), before
// (PATCHED=0) and after (PATCHED=1) build-utils/melonx/moltenvk/rewindbox-drawable-ownership.patch.
// Each function keeps the shape of its original; Metal objects are reference-counted fakes freed at
// zero, so a sanitizer sees a use after free where Objective-C would crash in objc_retain.
//   MeloNX: SynchronousQueueSubmits = false (MVKInitialization.cs), so presents run on MoltenVK's
//   submission thread while vkAcquireNextImageKHR runs on the render thread; acquireNextImage picks
//   the image with the shortest wait, available or not (MVKSwapchain.mm).
// Modes: "interleave" forces the reported order (acquire of the same image between the present's
// drawable read and the copy of its Metal handler blocks); "stress" runs both threads freely.
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <mutex>
#include <thread>
#include <vector>

static std::atomic<long> live{0}, vended{0};

struct Drawable {                       // CAMetalDrawable
	std::atomic<int> refs{1};
	int texture = 80;                     // .texture.pixelFormat
	Drawable() { live++; vended++; }
	~Drawable() { live--; }
};
static Drawable* retain(Drawable* d) { if (d) d->refs.fetch_add(1); return d; }   // objc_retain
static void release(Drawable* d) { if (d && d->refs.fetch_sub(1) == 1) delete d; } // objc_release

struct CommandBuffer {                  // MTLCommandBuffer: handler blocks, copied when added
	std::vector<std::function<void()>> scheduled, completed;
	std::vector<Drawable*> captured;
	void addHandler(std::vector<std::function<void()>>& list, Drawable* d, std::function<void(Drawable*)> body) {
		// _Block_copy -> _Block_object_assign -> objc_retain of the captured drawable
		Drawable* held = retain(d);
		int format = held ? held->texture : 0;   // the retain touches the object
		(void)format;
		captured.push_back(held);
		list.push_back([held, body] { body(held); });
	}
	void run() {
		for (auto& f : scheduled) f();
		for (auto& f : completed) f();
		for (auto* d : captured) release(d);     // the copied blocks are freed
	}
};

static std::function<void()> pause_after_read;   // the interleaving hook (between read and block copy)

struct Image {
	Drawable* _mtlDrawable = nullptr;
#if PATCHED
	std::mutex _mtlDrawableLock;
	Drawable* fetchCAMetalDrawable() { return new Drawable(); }          // nextDrawable, retained
	Drawable* getCAMetalDrawable() {
		{ std::lock_guard<std::mutex> l(_mtlDrawableLock); if (_mtlDrawable) return _mtlDrawable; }
		Drawable* fetched = fetchCAMetalDrawable(); Drawable* unused = nullptr; Drawable* d;
		{ std::lock_guard<std::mutex> l(_mtlDrawableLock);
		  if (_mtlDrawable) unused = fetched; else _mtlDrawable = fetched; d = _mtlDrawable; }
		release(unused); return d;
	}
	Drawable* takeCAMetalDrawable() {
		Drawable* d;
		{ std::lock_guard<std::mutex> l(_mtlDrawableLock); d = _mtlDrawable; _mtlDrawable = nullptr; }
		return d ? d : fetchCAMetalDrawable();
	}
	void releaseMetalDrawable() {
		Drawable* d;
		{ std::lock_guard<std::mutex> l(_mtlDrawableLock); d = _mtlDrawable; _mtlDrawable = nullptr; }
		release(d);
	}
	void acquireAndSignalWhenAvailable() { /* no drawable release: each present took its own */ }
	void presentCAMetalDrawable(CommandBuffer& cb) {
		Drawable* mtlDrwbl = takeCAMetalDrawable();
		if (pause_after_read) pause_after_read();
		cb.addHandler(cb.scheduled, mtlDrwbl, [](Drawable* d) { (void)d->texture; /* present */ });
		cb.addHandler(cb.completed, mtlDrwbl, [](Drawable*) {});
		cb.completed.push_back([mtlDrwbl] { release(mtlDrwbl); });   // the presentation's reference
	}
#else
	Drawable* getCAMetalDrawable() {
		if (!_mtlDrawable) _mtlDrawable = new Drawable();                 // [nextDrawable retain]
		return _mtlDrawable;
	}
	void releaseMetalDrawable() { release(_mtlDrawable); _mtlDrawable = nullptr; }
	void acquireAndSignalWhenAvailable() { releaseMetalDrawable(); }
	void presentCAMetalDrawable(CommandBuffer& cb) {
		Drawable* mtlDrwbl = getCAMetalDrawable();
		if (pause_after_read) pause_after_read();
		cb.addHandler(cb.scheduled, mtlDrwbl, [](Drawable* d) { (void)d->texture; });
		retain(mtlDrwbl);                                                  // [mtlDrwbl retain]
		cb.addHandler(cb.completed, mtlDrwbl, [](Drawable*) {});
		cb.completed.push_back([mtlDrwbl] { release(mtlDrwbl); });
	}
#endif
	void encodeDraw() { (void)getCAMetalDrawable()->texture; }          // getMTLTexture(0) while encoding
	void destroy() { releaseMetalDrawable(); }
};

int main(int argc, char** argv) {
	const char* mode = argc > 1 ? argv[1] : "interleave";
	Image image;
	if (!strcmp(mode, "interleave")) {
		// Frame k of image 0: drawn and presented on the submission thread; meanwhile the render thread
		// acquires image 0 again (no image available at an unbounded frame rate).
		std::atomic<int> step{0};
		pause_after_read = [&] { step = 1; while (step != 2) std::this_thread::yield(); };
		CommandBuffer cb;
		std::thread submission([&] { image.encodeDraw(); image.presentCAMetalDrawable(cb); cb.run(); });
		while (step != 1) std::this_thread::yield();
		image.acquireAndSignalWhenAvailable();
		step = 2;
		submission.join();
		pause_after_read = nullptr;
	} else {
		const int frames = argc > 2 ? atoi(argv[2]) : 20000;
		std::atomic<bool> done{false};
		std::thread render([&] { while (!done) image.acquireAndSignalWhenAvailable(); });
		for (int frame = 0; frame < frames; frame++) {
			CommandBuffer cb;
			image.encodeDraw(); image.presentCAMetalDrawable(cb); cb.run();
		}
		done = true; render.join();
	}
	image.destroy();
	printf("drawables vended %ld, still alive %ld\n", vended.load(), live.load());
	return live.load() == 0 ? 0 : 3;   // every drawable is released once its presentation completed
}
