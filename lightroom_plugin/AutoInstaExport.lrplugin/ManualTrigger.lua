local LrTasks = import 'LrTasks'
local LrDialogs = import 'LrDialogs'

local ExportTask = require 'ExportTask'

LrTasks.startAsyncTask(function()
    local ok, err = LrTasks.pcall(ExportTask.runExportPass)
    if ok then
        LrDialogs.showBezel('Auto Insta Export: pass complete')
    else
        LrDialogs.message('Auto Insta Export failed', tostring(err), 'critical')
    end
end)
