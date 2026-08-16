// main.cpp
// =============================================================================
// Standalone drawing tester for the spell engine
// =============================================================================
// A tiny local web server wrapped around ONE qrec::SpellEngine, so the
// recognizer can be drawn at without launching Godot. It compiles the engine
// sources straight out of mage-godot/scripts/spell_engine and loads the
// templates and spells out of mage-godot/assets, so what it answers is what
// the game would answer -- there is no second copy of anything to drift.
//
// The browser is only a pen and a screen here: it records strokes and posts
// them, and every recognition decision is made by the same C++ the game runs.
//
//   POST /stroke   body: one "x y" pair per line -> engine.add_stroke
//   POST /clear    -> engine.clear
//   GET  /state    -> current features + matched spell, no change
//   GET  /         -> page.html, read from disk per request so editing the
//                     page only needs a browser refresh, not a rebuild
//
// Single-threaded and bound to 127.0.0.1 on purpose: one canvas, one engine,
// one connection at a time, nothing listening beyond this machine.

#include <winsock2.h>
#include <ws2tcpip.h>
// windows.h and shellapi.h must follow winsock2.h -- windows.h drags in
// winsock 1 otherwise and the two sets of declarations collide.
#include <shellapi.h>
#include <windows.h>

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "scripts/spell_engine/spell_engine.hpp"

namespace fs = std::filesystem;

namespace {

constexpr unsigned short kPort = 8770;

// -----------------------------------------------------------------------
// Paths
// -----------------------------------------------------------------------

fs::path exe_dir() {
	char buffer[MAX_PATH];
	DWORD length = GetModuleFileNameA(nullptr, buffer, MAX_PATH);
	if (length == 0) {
		return fs::current_path();
	}
	return fs::path(std::string(buffer, length)).parent_path();
}

// SpellEngine loads its assets from paths relative to the working directory
// ("assets/spell_engine/..."), so the tester has to run from the Godot
// project directory the same way the game does. Rather than make that the
// caller's problem, find it and move there.
bool enter_project_dir(const fs::path& explicit_dir, fs::path* chosen) {
	std::vector<fs::path> candidates;
	if (!explicit_dir.empty()) {
		candidates.push_back(explicit_dir);
	} else {
		// tools/spell_tester/ -> repo root -> the Godot project.
		candidates.push_back(exe_dir().parent_path().parent_path() / "mage-godot");
		candidates.push_back(fs::current_path());
	}

	for (const fs::path& candidate : candidates) {
		std::error_code ec;
		if (fs::is_directory(candidate / "assets" / "spell_engine" / "templates", ec)) {
			fs::current_path(candidate, ec);
			if (!ec) {
				*chosen = fs::absolute(candidate);
				return true;
			}
		}
	}
	return false;
}

bool read_file(const fs::path& path, std::string* out) {
	std::ifstream in(path, std::ios::binary);
	if (!in) {
		return false;
	}
	std::ostringstream buffer;
	buffer << in.rdbuf();
	*out = buffer.str();
	return true;
}

// -----------------------------------------------------------------------
// Engine <-> JSON
// -----------------------------------------------------------------------

std::string json_escape(const std::string& text) {
	std::string out;
	out.reserve(text.size());
	for (char c : text) {
		switch (c) {
			case '"': out += "\\\""; break;
			case '\\': out += "\\\\"; break;
			case '\n': out += "\\n"; break;
			case '\r': out += "\\r"; break;
			case '\t': out += "\\t"; break;
			default: out += c; break;
		}
	}
	return out;
}

std::string number(double value) {
	char buffer[64];
	std::snprintf(buffer, sizeof(buffer), "%.4f", value);
	return buffer;
}

// Everything the page needs to redraw its readout: the features the engine
// currently holds (it only keeps ones that cleared their template's
// min_score, so this is already the "certain enough" set) and whichever
// spell those features add up to, if any.
std::string state_json(const qrec::SpellEngine& engine) {
	std::string json = "{\"features\":[";
	bool first = true;
	for (const auto& feature : engine.recognizer().features()) {
		if (!feature->result.name.has_value()) {
			continue;
		}
		// (min_x, max_x, min_y, max_y) -- see Feature::bounding_box.
		const std::array<double, 4>& box = feature->bounding_box();
		if (!first) {
			json += ',';
		}
		first = false;
		json += "{\"name\":\"" + json_escape(*feature->result.name) + "\"";
		json += ",\"score\":" + number(feature->result.score);
		json += ",\"min_score\":" + number(feature->result.min_score);
		json += ",\"level\":" + std::to_string(feature->level);
		json += ",\"cx\":" + number((box[0] + box[1]) * 0.5);
		json += ",\"cy\":" + number((box[2] + box[3]) * 0.5);
		json += '}';
	}
	json += "],\"spell\":\"" + json_escape(engine.match_spell()) + "\"}";
	return json;
}

// One "x y" pair per line, which is all the page ever sends. Anything
// unparseable is skipped rather than fatal -- a dropped point is a worse
// stroke, not a broken tester.
std::vector<qrec::Point> parse_stroke(const std::string& body) {
	std::vector<qrec::Point> points;
	std::istringstream lines(body);
	std::string line;
	while (std::getline(lines, line)) {
		std::istringstream fields(line);
		double x = 0.0;
		double y = 0.0;
		if (fields >> x >> y) {
			points.push_back(qrec::Point{x, y});
		}
	}
	return points;
}

// -----------------------------------------------------------------------
// Minimal HTTP
// -----------------------------------------------------------------------

struct Request {
	std::string method;
	std::string path;
	std::string body;
};

std::string to_lower(std::string text) {
	std::transform(text.begin(), text.end(), text.begin(),
				   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
	return text;
}

size_t content_length_of(const std::string& headers) {
	std::string lowered = to_lower(headers);
	size_t at = lowered.find("content-length:");
	if (at == std::string::npos) {
		return 0;
	}
	return static_cast<size_t>(std::strtoul(headers.c_str() + at + 15, nullptr, 10));
}

bool read_request(SOCKET client, Request* request) {
	std::string raw;
	char buffer[4096];

	// Headers first, then however much body Content-Length promised.
	size_t header_end = std::string::npos;
	while ((header_end = raw.find("\r\n\r\n")) == std::string::npos) {
		int received = recv(client, buffer, sizeof(buffer), 0);
		if (received <= 0) {
			return false;
		}
		raw.append(buffer, static_cast<size_t>(received));
	}
	header_end += 4;

	const size_t expected = content_length_of(raw.substr(0, header_end));
	std::string body = raw.substr(header_end);
	while (body.size() < expected) {
		int received = recv(client, buffer, sizeof(buffer), 0);
		if (received <= 0) {
			break;
		}
		body.append(buffer, static_cast<size_t>(received));
	}

	std::istringstream request_line(raw.substr(0, raw.find("\r\n")));
	request_line >> request->method >> request->path;
	request->body = std::move(body);
	return !request->method.empty();
}

void send_response(SOCKET client, const char* status, const char* content_type, const std::string& body) {
	std::ostringstream response;
	response << "HTTP/1.1 " << status << "\r\n"
			 << "Content-Type: " << content_type << "\r\n"
			 << "Content-Length: " << body.size() << "\r\n"
			 << "Cache-Control: no-store\r\n"
			 << "Connection: close\r\n\r\n"
			 << body;
	const std::string text = response.str();
	size_t sent = 0;
	while (sent < text.size()) {
		int wrote = send(client, text.data() + sent, static_cast<int>(text.size() - sent), 0);
		if (wrote <= 0) {
			return;
		}
		sent += static_cast<size_t>(wrote);
	}
}

void handle(SOCKET client, qrec::SpellEngine* engine, const fs::path& page_path) {
	Request request;
	if (!read_request(client, &request)) {
		return;
	}

	if (request.method == "GET" && (request.path == "/" || request.path == "/index.html")) {
		std::string page;
		if (read_file(page_path, &page)) {
			send_response(client, "200 OK", "text/html; charset=utf-8", page);
		} else {
			send_response(client, "500 Internal Server Error", "text/plain",
						  "could not read " + page_path.string());
		}
		return;
	}

	if (request.method == "POST" && request.path == "/stroke") {
		std::vector<qrec::Point> points = parse_stroke(request.body);
		// GlyphCanvas drops one-point strokes for the same reason: $Q's
		// resampling divides by the stroke's own length.
		if (points.size() >= 2) {
			engine->add_stroke(points);
		}
		send_response(client, "200 OK", "application/json", state_json(*engine));
		return;
	}

	if (request.method == "POST" && request.path == "/clear") {
		engine->clear();
		send_response(client, "200 OK", "application/json", state_json(*engine));
		return;
	}

	if (request.method == "GET" && request.path == "/state") {
		send_response(client, "200 OK", "application/json", state_json(*engine));
		return;
	}

	send_response(client, "404 Not Found", "text/plain", "no such thing here");
}

}  // namespace

int main(int argc, char** argv) {
	fs::path explicit_dir;
	bool open_browser = true;
	for (int i = 1; i < argc; ++i) {
		const std::string arg = argv[i];
		if (arg == "--no-browser") {
			open_browser = false;
		} else {
			explicit_dir = arg;
		}
	}

	fs::path project_dir;
	if (!enter_project_dir(explicit_dir, &project_dir)) {
		std::cerr << "spell_tester: could not find a Godot project with "
					 "assets/spell_engine/templates in it.\n"
					 "Pass the project directory as an argument, e.g.\n"
					 "  spell_tester.exe C:\\path\\to\\mage\\mage-godot\n";
		return 1;
	}
	// Resolved before the working directory matters to anyone else, and kept
	// next to the executable so the page can be edited without rebuilding.
	const fs::path page_path = exe_dir() / "page.html";

	std::cout << "spell_tester: assets from " << project_dir.string() << "\n";

	// Loads every template and spell exactly as the game does, logging each
	// one through the shimmed jenova::sdk::Output.
	qrec::SpellEngine engine;

	WSADATA wsa_data;
	if (WSAStartup(MAKEWORD(2, 2), &wsa_data) != 0) {
		std::cerr << "spell_tester: WSAStartup failed\n";
		return 1;
	}

	SOCKET listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
	if (listener == INVALID_SOCKET) {
		std::cerr << "spell_tester: could not create a socket\n";
		WSACleanup();
		return 1;
	}

	BOOL reuse = TRUE;
	setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char*>(&reuse), sizeof(reuse));

	sockaddr_in address{};
	address.sin_family = AF_INET;
	address.sin_port = htons(kPort);
	inet_pton(AF_INET, "127.0.0.1", &address.sin_addr);

	if (bind(listener, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == SOCKET_ERROR ||
		listen(listener, SOMAXCONN) == SOCKET_ERROR) {
		std::cerr << "spell_tester: port " << kPort << " is not available -- is another tester already running?\n";
		closesocket(listener);
		WSACleanup();
		return 1;
	}

	char url[64];
	std::snprintf(url, sizeof(url), "http://127.0.0.1:%u/", static_cast<unsigned>(kPort));
	std::cout << "spell_tester: drawing at " << url << "  (Ctrl+C here to stop)\n";
	if (open_browser) {
		ShellExecuteA(nullptr, "open", url, nullptr, nullptr, SW_SHOWNORMAL);
	}

	for (;;) {
		SOCKET client = accept(listener, nullptr, nullptr);
		if (client == INVALID_SOCKET) {
			continue;
		}
		handle(client, &engine, page_path);
		closesocket(client);
	}
}
