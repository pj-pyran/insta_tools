local LrTasks = import 'LrTasks'
local LrDialogs = import 'LrDialogs'
local LrLogger = import 'LrLogger'

local logger = LrLogger('AutoInstaExport')
logger:enable('logfile')
datetimeNow = os.date('%Y-%m-%d %H:%M:%S')
logger:info('ManualTrigger.lua loaded at ' .. datetimeNow)

local ExportTask = require 'ExportTask'

LrTasks.startAsyncTask(function()
    local ok, err = LrTasks.pcall(ExportTask.runExportPass)
    if ok then
        LrDialogs.showBezel('Auto Insta Export: pass complete')
    else
        LrDialogs.message('Auto Insta Export failed', tostring(err), 'critical')
    end
end)
