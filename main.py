from zmp.marketplace import ZapretMarketplaceClient
from zmp.device import get_device_id

def main():
    client = ZapretMarketplaceClient(device_id=get_device_id())

    catalog = client.list_projects(limit=5)
    print(catalog)

if __name__ == "__main__":
    main()
