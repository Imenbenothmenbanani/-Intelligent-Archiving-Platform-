import argparse
import sys

from bucket import (
    create_bucket,
    list_buckets,
    delete_bucket,
)

from object import (
    upload_file,
    list_files,
    delete_file,
    get_file_metadata,
    get_file_stream,
)


def main():
    parser = argparse.ArgumentParser(description="Ceph Storage CLI")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list-buckets")

    create = sub.add_parser("create-bucket")
    create.add_argument("name")

    delete = sub.add_parser("delete-bucket")
    delete.add_argument("name")

    lf = sub.add_parser("list-files")
    lf.add_argument("bucket")

    up = sub.add_parser("upload")
    up.add_argument("bucket")
    up.add_argument("file")
    up.add_argument("object")

    df = sub.add_parser("delete-file")
    df.add_argument("bucket")
    df.add_argument("object")

    meta = sub.add_parser("metadata")
    meta.add_argument("bucket")
    meta.add_argument("object")

    read = sub.add_parser("get")
    read.add_argument("bucket")
    read.add_argument("object")

    args = parser.parse_args()
    try:
        if args.command == "list-buckets":
            print(list_buckets())

        elif args.command == "create-bucket":
            print(create_bucket(args.name))

        elif args.command == "delete-bucket":
            print(delete_bucket(args.name))

        elif args.command == "list-files":
            print(list_files(args.bucket))

        elif args.command == "upload":
            print(upload_file(args.bucket, args.file, args.object))

        elif args.command == "delete-file":
            print(delete_file(args.bucket, args.object))

        elif args.command == "metadata":
            print(get_file_metadata(args.bucket, args.object))

        elif args.command == "get":
            print(get_file_stream(args.bucket, args.object))
    except EnvironmentError as e:
        print(f"Configuration Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()