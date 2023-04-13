function apply_redaction(tag, timestamp, record)

    local stringtoboolean={ ["true"]=true, ["false"]=false }

    local patterns = {
        '\'jdbc:postgresql://(.*)\'',
        'S3 storage, bucket location: (.*)',
        'Endpoint set to: s3-(.*)',
    }

    local is_logs_redaction = os.getenv("SPLUNK_LOGS_REDACTION")
    if is_logs_redaction == nil then
        is_logs_redaction = true
    else
        is_logs_redaction = stringtoboolean[is_logs_redaction]
    end

    if is_logs_redaction then
        table.insert(patterns, '[%w+%.%-_]+@[%w+%.%-_]+%.%a%a+') --email
    end
-- The simple form of email regex (not RFC 5322) is used due to
-- Lua doesn't support full functionality of regex.


    new_record = record
    local message = record["message"]

    for key, pattern in pairs(patterns) do
        message = string.gsub(message, pattern, '[SECRET REDACTED]')
    end

    new_record["message"] = message

    return 2, timestamp, new_record
end
