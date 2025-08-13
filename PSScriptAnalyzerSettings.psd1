# PSScriptAnalyzer Settings
# This file configures PSScriptAnalyzer for the project

@{
    # Only show Warning and Error severity
    Severity = @('Warning', 'Error')

    # Include all default rules
    IncludeDefaultRules = $true

    # Exclude specific rules if needed
    ExcludeRules = @(
        # Add any rules to exclude here
    )

    # Rules configuration
    Rules = @{
        # Respect suppression attributes in code
        PSAvoidUsingWriteHost = @{
            Enable = $true
        }
        PSUseApprovedVerbs = @{
            Enable = $true
        }
        PSAvoidUsingEmptyCatchBlock = @{
            Enable = $true
        }
        PSUseSingularNouns = @{
            Enable = $true
        }
        PSUseShouldProcessForStateChangingFunctions = @{
            Enable = $true
        }
    }
}
