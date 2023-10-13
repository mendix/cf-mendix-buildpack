function add_metadata(tag, timestamp, record)

    record["instance_index"] = os.getenv("CF_INSTANCE_INDEX") or ""
    record["environment_id"] = os.getenv("ENVIRONMENT") or ""
    record["hostname"] = os.getenv("FLUENTBIT_APP_HOSTNAME") or ""
    record["application_name"] = os.getenv("FLUENTBIT_APP_NAME") or ""
    record["runtime_version"] = os.getenv("FLUENTBIT_APP_RUNTIME_VERSION") or ""
    record["model_version"] = os.getenv("FLUENTBIT_APP_MODEL_VERSION") or ""

    local raw_tags = os.getenv("TAGS")
    if raw_tags then
        local tags_with_quotes = raw_tags:sub(2, raw_tags:len()-1)
        local str_tags = tags_with_quotes:gsub('"','')

        for item in str_tags:gmatch("([^,]+)") do
            for key, val in item:gmatch("([^:]*):?([^:]*)") do
                if (key and (key:gsub(' ','') ~= "")) then
                    record[key] = val
                end
            end
        end
    end

    return 2, timestamp, record
end
