function add_tags(tag, timestamp, record)

    local raw_tags = os.getenv("TAGS")
    local tags_with_quotes = raw_tags:sub(2, raw_tags:len()-1)
    local str_tags = tags_with_quotes:gsub('"','')

    for item in str_tags:gmatch("([^,]+)") do
        for key, val in item:gmatch("([^:]*):?([^:]*)") do
            if (key and (key:gsub(' ','') ~= "")) then
                record[key] = val
            end
        end
    end

    return 2, timestamp, record
end