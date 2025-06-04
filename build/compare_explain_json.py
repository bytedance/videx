import json
import sys

# NOTE: This comparison script is primarily designed for the EXPLAIN JSON structure 
# encountered in the CI check (e.g., for TPCH Q21). 
# For more complex EXPLAIN outputs involving UNIONs, complicated subqueries, 
# or views, its coverage and accuracy might be limited and may require enhancements.

def compare_query_blocks(block1, block2, path="query_block"):
    """
    Recursively compares two query blocks from the EXPLAIN JSON.
    Stops and returns an error string immediately if an error is found, otherwise None.
    """
    # Compare select_id (if present)
    if block1.get("select_id") != block2.get("select_id"):
        return f"{path}: 'select_id' mismatch: {block1.get('select_id')} vs {block2.get('select_id')}"

    # Check for presence of cost_info, but don't compare values
    if ("cost_info" in block1) != ("cost_info" in block2):
        return f"{path}: 'cost_info' presence differs."

    # Compare table/operation structure, handle different possible top-level keys like 'ordering_operation', 'grouping_operation', 'nested_loop', 'table'
    op1_type, op1_details = get_operation_details(block1)
    op2_type, op2_details = get_operation_details(block2)

    if op1_type != op2_type:
        return f"{path}: Operation type mismatch: {op1_type} vs {op2_type}"

    if op1_type == "table":
        table_error = compare_table_access(op1_details, op2_details, f"{path}.table")
        if table_error:
            return table_error
    elif op1_type == "nested_loop":
        if len(op1_details) != len(op2_details):
            return f"{path}.nested_loop: Number of join stages mismatch: {len(op1_details)} vs {len(op2_details)}"
        else:
            for i, (t1, t2) in enumerate(zip(op1_details, op2_details)):
                table_error = compare_table_access(t1.get("table"), t2.get("table"), f"{path}.nested_loop[{i}].table")
                if table_error:
                    return table_error
    elif op1_type == "grouping_operation" or op1_type == "ordering_operation":
        if op1_details.get("using_temporary_table") != op2_details.get("using_temporary_table"):
            return f"{path}.{op1_type}: 'using_temporary_table' mismatch."
        if op1_details.get("using_filesort") != op2_details.get("using_filesort"):
             return f"{path}.{op1_type}: 'using_filesort' mismatch."
        
        # Recursively compare the underlying operation
        underlying_error = compare_query_blocks(op1_details, op2_details, f"{path}.{op1_type}")
        if underlying_error:
            return underlying_error

    return None # No errors found

def get_operation_details(block):
    """Identifies the main operation in a query block."""
    if "table" in block:
        return "table", block["table"]
    if "nested_loop" in block:
        return "nested_loop", block["nested_loop"]
    if "grouping_operation" in block:
        return "grouping_operation", block["grouping_operation"]
    if "ordering_operation" in block:
        if "grouping_operation" in block["ordering_operation"]:
             return "grouping_operation", block["ordering_operation"]["grouping_operation"]
        if "nested_loop" in block["ordering_operation"]:
             return "nested_loop", block["ordering_operation"]["nested_loop"]
        if "table" in block["ordering_operation"]:
             return "table", block["ordering_operation"]["table"]
        return "ordering_operation", block["ordering_operation"] # Fallback
    return "unknown", block


def compare_table_access(table1, table2, path="table"):
    """
    Compares key properties of a table access.
    Stops and returns an error string immediately if an error is found, otherwise None.
    """
    if not table1 or not table2:
        if not table1 and not table2:
            return None # Both are None, no error
        return f"{path}: One table is None, other is not. t1: {table1 is not None}, t2: {table2 is not None}"

    props_to_compare = [
        "table_name",
        "access_type",
        "key"
    ]

    for prop in props_to_compare:
        val1 = table1.get(prop)
        val2 = table2.get(prop)
        if val1 != val2:
            return f"{path}.{prop}: Mismatch: '{val1}' vs '{val2}'"
    
    # Compare possible_keys as sets if they exist
    pk1 = set(table1.get("possible_keys", []))
    pk2 = set(table2.get("possible_keys", []))
    if pk1 != pk2:
        return f"{path}.possible_keys: Mismatch: {sorted(list(pk1))} vs {sorted(list(pk2))}"

    # Compare used_key_parts carefully
    ukp1 = table1.get("used_key_parts")
    ukp2 = table2.get("used_key_parts")
    if isinstance(ukp1, list) and isinstance(ukp2, list):
        if set(ukp1) != set(ukp2):
             return f"{path}.used_key_parts: Mismatch: {ukp1} vs {ukp2}"
    elif ukp1 != ukp2: # Handles cases where one might be None
        return f"{path}.used_key_parts: Mismatch: {ukp1} vs {ukp2}"

    # Handling for 'not_exists', 'first_match'
    for semi_join_prop in ["not_exists", "first_match"]:
        if table1.get(semi_join_prop) != table2.get(semi_join_prop):
             return f"{path}.{semi_join_prop}: Mismatch: {table1.get(semi_join_prop)} vs {table2.get(semi_join_prop)}"
             
    return None # No errors found

def main():
    if len(sys.argv) != 3:
        print("Usage: python compare_explain_json.py <file1.json> <file2.json>")
        sys.exit(1)

    file_path1 = sys.argv[1]
    file_path2 = sys.argv[2]

    try:
        with open(file_path1, 'r') as f1:
            data1 = json.load(f1)
        with open(file_path2, 'r') as f2:
            data2 = json.load(f2)
    except FileNotFoundError as e:
        print(f"Error: {e.filename} not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        sys.exit(1)

    if "query_block" not in data1 or "query_block" not in data2:
        print("Error: Both JSON files must contain a 'query_block' top-level key.")
        sys.exit(1)

    comparison_error = compare_query_blocks(data1["query_block"], data2["query_block"])

    if comparison_error is None:
        print("JSON structure match successfully.")
        sys.exit(0)
    else:
        print("JSON structure mismatch:")
        print(f"- {comparison_error}")
        sys.exit(1)

if __name__ == "__main__":
    main() 