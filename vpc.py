import boto3
import pprint
import sys
ec2_client = boto3.client('ec2')
ec2_res    = boto3.resource('ec2')

def createVpc(offset):
    vpc = ec2_res.create_vpc(CidrBlock = '10.' + str(offset) + '.0.0/16')
    vpc.create_tags(
        Tags = [ { 'Key': 'Name', 'Value': 'VPC-' + str(offset) }, ]
    )
    vpc.wait_until_available()
    return(vpc)

def destroyVpc(vpcid):
    print('Removing VPC ({}) from AWS'.format(vpcid))
    ec2 = boto3.resource('ec2')
    ec2client = ec2.meta.client
    vpc = ec2.Vpc(vpcid)
    # detach and delete all gateways associated with the vpc
    for gw in vpc.internet_gateways.all():
        print('Removing igw {}'.format(gw.id))
        vpc.detach_internet_gateway(InternetGatewayId=gw.id)
        gw.delete()
    # delete all route table associations
    for rt in vpc.route_tables.all():
        for rta in rt.associations:
            if not rta.main:
                rta.delete()
    # delete any instances
    for subnet in vpc.subnets.all():
        for instance in subnet.instances.all():
            instance.terminate()
    # delete our endpoints
    for ep in ec2client.describe_vpc_endpoints(
            Filters=[{
                'Name': 'vpc-id',
                'Values': [vpcid]
            }])['VpcEndpoints']:
        ec2client.delete_vpc_endpoints(VpcEndpointIds=[ep['VpcEndpointId']])
    # delete our security groups
    for sg in vpc.security_groups.all():
        if sg.group_name != 'default':
            sg.delete()
    # delete any vpc peering connections
    for vpcpeer in ec2client.describe_vpc_peering_connections(
            Filters=[{
                'Name': 'requester-vpc-info.vpc-id',
                'Values': [vpcid]
            }])['VpcPeeringConnections']:
        ec2.VpcPeeringConnection(vpcpeer['VpcPeeringConnectionId']).delete()
    # delete non-default network acls
    for netacl in vpc.network_acls.all():
        if not netacl.is_default:
            netacl.delete()
    # delete network interfaces
    for subnet in vpc.subnets.all():
        for interface in subnet.network_interfaces.all():
            interface.delete()
        subnet.delete()
    # finally, delete the vpc
    ec2client.delete_vpc(VpcId=vpcid)
    print("    VPC deleted")

def bulkCreate(qty):
    vpc_id_list = []
    for i in range(qty):
        vpc = createVpc(i)
        print("Created VPC {}".format(vpc.id))
        igw = ec2_res.create_internet_gateway()
        vpc.attach_internet_gateway(InternetGatewayId=igw.id)
        default_rt = ec2_client.describe_route_tables(Filters=[{'Name': 'vpc-id','Values': [vpc.id,]},])['RouteTables'][0]['RouteTableId']
        print("   default route table is is {}".format(default_rt))
        rt = ec2_res.RouteTable(default_rt)
        route = rt.create_route(DestinationCidrBlock='0.0.0.0/0',
				               GatewayId = igw.id)
        subnetString = "10.{}.{}.0/24".format(i,i)
        subnet = ec2_res.create_subnet(CidrBlock=subnetString, VpcId=vpc.id)
        rt.associate_with_subnet(SubnetId=subnet.id)
	
        sec_group = ec2_res.create_security_group(GroupName='slice_0', 
						  Description='slice_0 sec group', 
						  VpcId=vpc.id)
        sec_group.authorize_ingress(CidrIp='0.0.0.0/0',
				    IpProtocol='icmp', 
				    FromPort=-1,
				    ToPort=-1)
        vpc_id_list.append(vpc.id)
    return(vpc_id_list)
        
allVpcs = ec2_client.describe_vpcs()['Vpcs']
print("Found {} VPCs".format(len(allVpcs)))
for vpc in allVpcs:
    print("VPC id {}".format(vpc['VpcId']))

vpcList = bulkCreate(4)

user = input("Delete VPCs now [Y/y]")
for vpc in vpcList:
    destroyVpc(vpc)
