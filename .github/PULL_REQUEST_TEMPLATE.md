## Pull Request Summary

[Provide a clear and concise summary of your changes (1-3 sentences)]

## Related Issues

Resolves: #[Insert issue number(s)]

## Detailed Description

[Explain your changes in detail, including:

- What problem does this PR solve?
- How does your solution work?
- Any trade-offs or alternative approaches considered?]

**Important: Before submitting, please complete the description above and review the checklist below.**

---

<details>
<summary><strong>Contribution Guidelines (Expand for Details)</strong></summary>

<p>We appreciate your contribution to VIDEX! To ensure a smooth review process and maintain high code quality, please adhere to the following guidelines:</p>

<h3>Pull Request Title Format</h3>
<p>Your PR title should start with one of these prefixes to indicate the nature of the change:</p>
<ul>
    <li><code>[Core]</code>: Changes to core engine functionality</li>
    <li><code>[Optimizer]</code>: Changes to VIDEX-Optimizer-Plugin</li>
    <li><code>[Stats]</code>: Changes to VIDEX-Statistic-Server</li>
    <li><code>[Algorithm]</code>: Implementation of new algorithms for NDV, cardinality estimation, etc.</li>
    <li><code>[Pipeline]</code>: Enhancements to the pipeline (e.g., data collection, environment setup)</li>
    <li><code>[Bug]</code>: Corrections to existing functionality</li>
    <li><code>[CI]</code>: Changes to build process or CI pipeline</li>
    <li><code>[Docs]</code>: Updates or additions to documentation</li>
    <li><code>[Test]</code>: Adding or updating tests</li>
    <li><code>[Perf]</code>: Performance improvements</li>
    <li><code>[Misc]</code>: For changes not covered above (use sparingly)</li>
</ul>
<p><em>Note: For changes spanning multiple categories, use the most specific prefix or multiple prefixes in order of importance (e.g., [Algorithm][Stats]).</em></p>

<h3>Submission Checklist</h3>
<ul>
    <li>[ ] PR title includes appropriate prefix(es)</li>
    <li>[ ] Changes are clearly explained in the PR description</li>
    <li>[ ] New and existing tests pass successfully</li>
    <li>[ ] Code adheres to project style and best practices</li>
    <li>[ ] Documentation updated to reflect changes (if applicable)</li>
    <li>[ ] Changes have been tested on both Plugin-Mode and Standalone-Mode (if applicable)</li>
    <li>[ ] Statistical accuracy has been verified (for algorithm or optimizer changes)</li>
    <li>[ ] No regression in query plan accuracy compared to InnoDB (if applicable)</li>
    <li>[ ] Performance benchmarks conducted (for performance-sensitive changes)</li>
</ul>

<p>By submitting this PR, you confirm that you've read these guidelines and your changes align with the project's contribution standards.</p>

</details>