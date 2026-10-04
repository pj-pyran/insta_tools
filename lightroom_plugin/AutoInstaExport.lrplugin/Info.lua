return {
    LrSdkVersion = 13.0,
    LrSdkMinimumVersion = 6.0,
    LrToolkitIdentifier = 'com.pjpyran.autoinstaexport',
    LrPluginName = 'Auto Insta Export',
    LrInitPlugin = 'Init.lua',

    LrLibraryMenuItems = {
        {
            title = 'Auto Insta Export: Run Now',
            file = 'ManualTrigger.lua',
        },
        {
            title = 'Auto Insta Export: Toggle Auto-Export On/Off',
            file = 'ToggleEnabled.lua',
        },
    },

    VERSION = { major = 1, minor = 1, revision = 1, build = 7 },
}
