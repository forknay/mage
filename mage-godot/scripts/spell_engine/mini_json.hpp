// mini_json.hpp
// =============================================================================
// A tiny, dependency-free JSON reader.
// =============================================================================
// Supports exactly what spell_engine.cpp's asset loader needs: objects,
// arrays, strings, numbers, booleans, null. No writer, no comments, no
// trailing commas -- strict JSON in, a simple DOM-ish Value out.
//
// Not a general-purpose JSON library; if your project already has one
// (nlohmann/json, rapidjson, etc.) prefer that instead and delete this
// file. This exists purely so spell_engine.cpp has zero external
// dependencies.
#pragma once

#include <cctype>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace minijson {

class Value {
public:
	enum class Type { Null, Bool, Number, String, Array, Object };

	Value() = default;
	Value(std::nullptr_t) {}
	explicit Value(bool b) : type_(Type::Bool), bool_(b) {}
	explicit Value(double d) : type_(Type::Number), num_(d) {}
	explicit Value(std::string s) : type_(Type::String), str_(std::move(s)) {}

	static Value make_array() {
		Value v;
		v.type_ = Type::Array;
		return v;
	}
	static Value make_object() {
		Value v;
		v.type_ = Type::Object;
		return v;
	}

	Type type() const { return type_; }
	bool is_null() const { return type_ == Type::Null; }

	// -- Object access --------------------------------------------------
	bool contains(const std::string& key) const { return type_ == Type::Object && obj_.count(key) > 0; }

	const Value& at(const std::string& key) const {
		if (type_ != Type::Object) throw std::runtime_error("mini_json: not an object");
		auto it = obj_.find(key);
		if (it == obj_.end()) throw std::runtime_error("mini_json: missing key '" + key + "'");
		return it->second;
	}

	Value& set(const std::string& key, Value v) {
		type_ = Type::Object;
		return obj_[key] = std::move(v);
	}

	// -- Array access -----------------------------------------------------
	void push_back(Value v) {
		type_ = Type::Array;
		arr_.push_back(std::move(v));
	}
	std::vector<Value>::const_iterator begin() const { return arr_.begin(); }
	std::vector<Value>::const_iterator end() const { return arr_.end(); }

	size_t size() const {
		if (type_ == Type::Array) return arr_.size();
		if (type_ == Type::Object) return obj_.size();
		return 0;
	}
	bool empty() const { return size() == 0; }

	// -- Typed getters ------------------------------------------------------
	template <typename T>
	T get() const;

	template <typename T>
	T value(const std::string& key, T default_value) const {
		if (!contains(key) || at(key).is_null()) return default_value;
		return at(key).get<T>();
	}

private:
	Type type_ = Type::Null;
	bool bool_ = false;
	double num_ = 0.0;
	std::string str_;
	std::vector<Value> arr_;
	std::map<std::string, Value> obj_;
};

template <>
inline double Value::get<double>() const {
	if (type_ != Type::Number) throw std::runtime_error("mini_json: value is not a number");
	return num_;
}
template <>
inline int Value::get<int>() const {
	return static_cast<int>(get<double>());
}
template <>
inline std::string Value::get<std::string>() const {
	if (type_ != Type::String) throw std::runtime_error("mini_json: value is not a string");
	return str_;
}
template <>
inline bool Value::get<bool>() const {
	if (type_ != Type::Bool) throw std::runtime_error("mini_json: value is not a bool");
	return bool_;
}

// =============================================================================
// Parser (recursive descent, strict JSON)
// =============================================================================
class Parser {
public:
	explicit Parser(std::string text) : s_(std::move(text)) {}

	Value parse() {
		skip_ws();
		Value v = parse_value();
		skip_ws();
		if (pos_ != s_.size()) throw std::runtime_error("mini_json: trailing content after top-level value");
		return v;
	}

private:
	std::string s_;
	size_t pos_ = 0;

	char peek() const {
		if (pos_ >= s_.size()) throw std::runtime_error("mini_json: unexpected end of input");
		return s_[pos_];
	}
	char take() {
		char c = peek();
		++pos_;
		return c;
	}
	void skip_ws() {
		while (pos_ < s_.size() && std::isspace(static_cast<unsigned char>(s_[pos_]))) ++pos_;
	}
	void expect(char c) {
		char got = take();
		if (got != c) throw std::runtime_error(std::string("mini_json: expected '") + c + "' but got '" + got + "'");
	}

	Value parse_value() {
		skip_ws();
		switch (peek()) {
			case '{':
				return parse_object();
			case '[':
				return parse_array();
			case '"':
				return Value(parse_string());
			case 't':
			case 'f':
				return parse_bool();
			case 'n':
				return parse_null();
			default:
				return parse_number();
		}
	}

	Value parse_object() {
		expect('{');
		Value obj = Value::make_object();
		skip_ws();
		if (peek() == '}') {
			take();
			return obj;
		}
		while (true) {
			skip_ws();
			std::string key = parse_string();
			skip_ws();
			expect(':');
			obj.set(key, parse_value());
			skip_ws();
			char c = take();
			if (c == ',') continue;
			if (c == '}') break;
			throw std::runtime_error("mini_json: expected ',' or '}' in object");
		}
		return obj;
	}

	Value parse_array() {
		expect('[');
		Value arr = Value::make_array();
		skip_ws();
		if (peek() == ']') {
			take();
			return arr;
		}
		while (true) {
			arr.push_back(parse_value());
			skip_ws();
			char c = take();
			if (c == ',') continue;
			if (c == ']') break;
			throw std::runtime_error("mini_json: expected ',' or ']' in array");
		}
		return arr;
	}

	std::string parse_string() {
		expect('"');
		std::string out;
		while (true) {
			char c = take();
			if (c == '"') break;
			if (c != '\\') {
				out += c;
				continue;
			}
			char esc = take();
			switch (esc) {
				case '"': out += '"'; break;
				case '\\': out += '\\'; break;
				case '/': out += '/'; break;
				case 'b': out += '\b'; break;
				case 'f': out += '\f'; break;
				case 'n': out += '\n'; break;
				case 'r': out += '\r'; break;
				case 't': out += '\t'; break;
				case 'u': out += parse_unicode_escape(); break;
				default: throw std::runtime_error("mini_json: bad escape sequence");
			}
		}
		return out;
	}

	// Parses a \uXXXX escape and returns its UTF-8 encoding. Only handles
	// the basic multilingual plane (no surrogate pairs) -- sufficient for
	// the plain-ASCII shape/spell names this loader deals with.
	std::string parse_unicode_escape() {
		unsigned int cp = 0;
		for (int i = 0; i < 4; ++i) {
			char h = take();
			cp <<= 4;
			if (h >= '0' && h <= '9') cp |= static_cast<unsigned int>(h - '0');
			else if (h >= 'a' && h <= 'f') cp |= static_cast<unsigned int>(h - 'a' + 10);
			else if (h >= 'A' && h <= 'F') cp |= static_cast<unsigned int>(h - 'A' + 10);
			else throw std::runtime_error("mini_json: bad hex digit in \\u escape");
		}
		std::string out;
		if (cp < 0x80) {
			out += static_cast<char>(cp);
		} else if (cp < 0x800) {
			out += static_cast<char>(0xC0 | (cp >> 6));
			out += static_cast<char>(0x80 | (cp & 0x3F));
		} else {
			out += static_cast<char>(0xE0 | (cp >> 12));
			out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
			out += static_cast<char>(0x80 | (cp & 0x3F));
		}
		return out;
	}

	Value parse_bool() {
		if (s_.compare(pos_, 4, "true") == 0) {
			pos_ += 4;
			return Value(true);
		}
		if (s_.compare(pos_, 5, "false") == 0) {
			pos_ += 5;
			return Value(false);
		}
		throw std::runtime_error("mini_json: invalid literal");
	}

	Value parse_null() {
		if (s_.compare(pos_, 4, "null") == 0) {
			pos_ += 4;
			return Value(nullptr);
		}
		throw std::runtime_error("mini_json: invalid literal");
	}

	Value parse_number() {
		size_t start = pos_;
		if (peek() == '-') take();
		while (pos_ < s_.size() && std::isdigit(static_cast<unsigned char>(s_[pos_]))) take();
		if (pos_ < s_.size() && s_[pos_] == '.') {
			take();
			while (pos_ < s_.size() && std::isdigit(static_cast<unsigned char>(s_[pos_]))) take();
		}
		if (pos_ < s_.size() && (s_[pos_] == 'e' || s_[pos_] == 'E')) {
			take();
			if (pos_ < s_.size() && (s_[pos_] == '+' || s_[pos_] == '-')) take();
			while (pos_ < s_.size() && std::isdigit(static_cast<unsigned char>(s_[pos_]))) take();
		}
		std::string num_str = s_.substr(start, pos_ - start);
		if (num_str.empty() || num_str == "-") throw std::runtime_error("mini_json: invalid number");
		try {
			return Value(std::stod(num_str));
		} catch (const std::exception&) {
			throw std::runtime_error("mini_json: invalid number '" + num_str + "'");
		}
	}
};

inline Value parse(const std::string& text) { return Parser(text).parse(); }

}  // namespace minijson