#include "videx_json_item.h"

/**
 * A simple parsing function is written here instead,
 * since rapid_json always encounters strange segmentation faults across platforms,
 *
 * @param json
 * @param code
 * @param message
 * @param data_dict
 * @return
 */
int videx_parse_simple_json(const std::string &json, int &code, std::string &message,
                      std::map<std::string, std::string> &data_dict) {
    try {
        // find code and message
        std::size_t pos_code = json.find("\"code\":");
        std::size_t pos_message = json.find("\"message\":");
        std::size_t pos_data = json.find("\"data\":");

        if (pos_code == std::string::npos || pos_message == std::string::npos || pos_data == std::string::npos) {
            throw std::invalid_argument("Missing essential components in JSON.");
        }

        // parse code
        std::size_t start = json.find_first_of("0123456789", pos_code);
        std::size_t end = json.find(',', start);
        code = std::stoi(json.substr(start, end - start));

        // parse message
        start = json.find('\"', pos_message + 10) + 1;
        end = json.find('\"', start);
        message = json.substr(start, end - start);

        // parse data
        start = json.find('{', pos_data) + 1;
        end = json.find('}', start);
        std::string data_content = json.substr(start, end - start);
        std::istringstream data_stream(data_content);
        std::string line;

        while (std::getline(data_stream, line, ',')) {
            std::size_t colon_pos = line.find(':');
            if (colon_pos == std::string::npos) {
                continue; // Skip malformed line
            }
            std::string key = line.substr(0, colon_pos);
            std::string value = line.substr(colon_pos + 1);

            // clean key 和 value
            auto trim_quotes_and_space = [](std::string &str) {
                // Trim whitespace and surrounding quotes
                size_t first = str.find_first_not_of(" \t\n\"");
                size_t last = str.find_last_not_of(" \t\n\"");
                if (first == std::string::npos || last == std::string::npos) {
                    str.clear(); // All whitespace or empty
                } else {
                    str = str.substr(first, last - first + 1);
                }
            };

            trim_quotes_and_space(key);
            trim_quotes_and_space(value);

            data_dict[key] = value;
        }

        return 0;
    } catch (std::exception &e) {
        std::cerr << "Failed to parse JSON: " << e.what() << std::endl;
        message = e.what();
        code = -1;
        return 1;
    }
}


/**
 * This function is used to escape double quotes in a string.
 * @param input
 * @param len
 * @return
 */
std::string videx_escape_double_quotes(const std::string &input, size_t len) {
    if (len == std::string::npos) len = input.length();

    //  if (len > input.length()) {
    //    throw std::invalid_argument("Length exceeds input string size");
    //  }

    std::string output = input.substr(0, len);
    size_t pos = output.find('\\');
    while (pos != std::string::npos) {
        output.replace(pos, 1, "\\\\");
        pos = output.find('\\', pos + 2);
    }
    // replace "
    pos = output.find('\"');
    while (pos != std::string::npos) {
        output.replace(pos, 1, "\\\"");
        pos = output.find('\"', pos + 2);
    }

    // replace \n with space
    pos = output.find('\n');
    while (pos != std::string::npos) {
        output.replace(pos, 1, " ");
        pos = output.find('\n', pos + 1);
    }

    // replace \t with space
    pos = output.find('\t');
    while (pos != std::string::npos) {
        output.replace(pos, 1, " ");
        pos = output.find('\t', pos + 1);
    }
    return output;
}

char* videx_server = nullptr;

size_t write_callback(void *contents, size_t size, size_t nmemb, std::string *outString) {
    size_t totalSize = size * nmemb;
    outString->append((char *) contents, totalSize);
    return totalSize;
}

int ask_from_videx_http(VidexJsonItem &request, VidexStringMap &res_json){
    const char *host_ip = "127.0.0.1:5001";
    char value[1000];
    
    //VIDEX_SERVER
    if(videx_server)
        host_ip = value;
    std::string url = std::string("http://") + host_ip + "/ask_videx";
    CURL *curl;
    CURLcode res_code;
    std::string readBuffer;
    curl = curl_easy_init(); // 初始化一个CURL easy handle。
    if(curl) {
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_POST, 1);


        std::string request_str = request.to_json();
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, request_str.c_str());

        // Set the headers
        struct curl_slist *headers = NULL;
        headers = curl_slist_append(headers, "Content-Type: application/json");
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &readBuffer);

        // Set the connection timeout to 10 seconds.
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
        // Set the overall request timeout to 30 seconds.
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);

        // Disallow connection reuse, so libcurl will close the connection immediately after completing a request.
        curl_easy_setopt(curl, CURLOPT_FORBID_REUSE, 1L);

        res_code = curl_easy_perform(curl);
        if (res_code != CURLE_OK) {
            std::cout << "access videx_server failed res_code != curle_ok: " << host_ip << std::endl;
            fprintf(stderr, "curl_easy_perform() failed: %s\n", curl_easy_strerror(res_code));
            return 1;
        } else {
            int code;
            std::string message;
            int error = videx_parse_simple_json(readBuffer.c_str(), code, message, res_json);
            if (error) {
                std::cout << "!__!__!__!__!__! JSON parse error: " << message << '\n';
                return 1;
            } else {
                if (message == "OK") {
                    std::cout << "access videx_server success: " << host_ip << std::endl;
                    return 0;
                } else {
                    std::cout << "access videx_server success but msg != OK: " << readBuffer.c_str() << std::endl;
                    return 1;
                }
            }
        }
    }
    std::cout << "access videx_server failed curl = false: " << host_ip << std::endl;
    return 1;
}